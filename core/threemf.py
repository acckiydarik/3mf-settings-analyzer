"""ThreeMF file analyzer -- extracts slicer settings from .3mf archives."""

import json
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Use defusedxml to prevent XXE attacks - required dependency
try:
    import defusedxml.ElementTree as ET
except ImportError:
    raise ImportError(
        "Required package 'defusedxml' is not installed. "
        "Install it with: pip install defusedxml"
    )

from core.constants import (
    BOOL_TRUE,
    DEFAULT_EXTRUDER,
    DEFAULT_IDENTIFY_ID,
    INFILL_DENSITY_KEYS,
    SYSTEM_KEYS,
    build_common_profile,
)

logger = logging.getLogger(__name__)


def _is_custom(obj_val: Any, global_val: Any) -> bool:
    """Check if object value differs from global profile value."""
    if obj_val is None:
        return False
    
    # Try numeric comparison first to handle 1.0 vs "1.0" correctly
    try:
        obj_num = float(obj_val)
        global_num = float(global_val)
        return obj_num != global_num
    except (ValueError, TypeError):
        # Fall back to string comparison for non-numeric values
        return str(obj_val) != str(global_val)


class ThreeMFAnalyzer:
    """Analyzes 3MF files and extracts slicer settings."""

    def __init__(self, filepath: Union[str, Path]):
        self.filepath = Path(filepath)
        self.temp_dir: Optional[Path] = None
        self.project_settings: Dict = {}
        self.objects: Dict[str, Dict] = {}
        self.plates: List[Dict] = []

    def analyze(self) -> Dict[str, Any]:
        """Main analysis method. Extracts and returns all settings from the 3MF file."""
        logger.debug("Starting analysis of file: %s", self.filepath)
        # Use TemporaryDirectory context manager for robust cleanup
        with tempfile.TemporaryDirectory() as temp_dir:
            self.temp_dir = Path(temp_dir)
            try:
                self._extract()
                self._parse_project_settings()
                self._parse_model_settings()
                result = self._build_result()
                logger.debug("Successfully analyzed %d objects", len(self.objects))
                return result
            except Exception:
                # Context manager handles directory cleanup
                raise

    def _extract(self):
        """Extract 3MF archive with Zip Slip protection.

        Validates all paths in the archive to prevent path traversal attacks.
        Uses a temporary directory managed by the caller.

        Raises:
            ValueError: If archive contains unsafe paths (Zip Slip attack).
            zipfile.BadZipFile: If the file is not a valid ZIP archive.
            OSError: If extraction fails due to filesystem issues.
        """
        if not self.temp_dir:
            raise RuntimeError("Temporary directory not initialized")

        try:
            with zipfile.ZipFile(self.filepath, 'r') as z:
                # Zip Slip protection: validate all paths before extraction
                for member in z.namelist():
                    # Check for absolute paths (leading slash/backslash) before creating Path
                    # Note: Path.is_absolute() behaves differently on Windows vs Unix
                    if member.startswith(('/', '\\')):
                        raise ValueError(f"Unsafe absolute path in archive: {member}")
                    member_path = Path(member)
                    # Check for OS-specific absolute paths (e.g., C:\ on Windows)
                    if member_path.is_absolute():
                        raise ValueError(f"Unsafe absolute path in archive: {member}")
                    # Resolve and check if path stays within temp_dir
                    target_path = (self.temp_dir / member).resolve()
                    if not target_path.is_relative_to(self.temp_dir.resolve()):
                        raise ValueError(f"Path traversal detected in archive: {member}")
                z.extractall(self.temp_dir)
        except zipfile.BadZipFile as e:
            raise zipfile.BadZipFile(f"Invalid or corrupted 3MF file: {self.filepath}") from e
        except OSError as e:
            raise OSError(f"Failed to extract 3MF archive '{self.filepath}': {e}") from e
        except Exception as e:
            if isinstance(e, ValueError): 
                raise # Re-raise security errors as-is
            logger.error("Unexpected error extracting '%s': %s", self.filepath, e)
            raise

    def _parse_project_settings(self):
        """Parse project_settings.config (JSON).

        Raises:
            json.JSONDecodeError: If the config file contains invalid JSON.
            OSError: If the file cannot be read.
        """
        config_path = self.temp_dir / "Metadata" / "project_settings.config"
        if config_path.exists():
            logger.debug("Parsing project settings from: %s", config_path)
            try:
                with open(config_path, 'r', encoding='utf-8', errors='replace') as f:
                    self.project_settings = json.load(f)
            except json.JSONDecodeError as e:
                raise json.JSONDecodeError(
                    f"Invalid JSON in project_settings.config: {e.msg}",
                    e.doc, e.pos
                ) from e
            except OSError as e:
                raise OSError(f"Failed to read project settings: {config_path}") from e
        else:
            logger.warning("Project settings file not found: %s", config_path)

    def _parse_model_settings(self):
        """Parse model_settings.config (XML).

        Raises:
            ET.ParseError: If the config file contains invalid XML.
        """
        config_path = self.temp_dir / "Metadata" / "model_settings.config"
        if not config_path.exists():
            logger.warning("Model settings file not found: %s", config_path)
            return

        logger.debug("Parsing model settings from: %s", config_path)

        try:
            tree = ET.parse(config_path)
            root = tree.getroot()
        except ET.ParseError as e:
            # ET.ParseError inherits from SyntaxError and doesn't accept custom messages.
            # Log context and re-raise the original exception.
            logger.error("Invalid XML in model_settings.config: %s", e)
            raise

        # Validate root element
        if root.tag != 'config':
            logger.warning(
                "Unexpected root element '%s' in model_settings.config, expected 'config'",
                root.tag,
            )

        # Parse all objects
        for obj in root.findall('.//object'):
            obj_id = obj.get('id')

            obj_data = {
                'name': None,
                'extruder': DEFAULT_EXTRUDER,
                'layer_height': None,
                'wall_loops': None,
                'sparse_infill_density': None,
                'enable_support': None,
                'brim_type': None,
                'outer_wall_speed': None,
                'inner_wall_speed': None,
                'custom_settings': {},
                'parts': []
            }

            for meta in obj.findall('metadata'):
                key = meta.get('key')
                value = meta.get('value')

                if key == 'name':
                    obj_data['name'] = value
                elif key == 'extruder':
                    obj_data['extruder'] = value
                elif key == 'layer_height':
                    obj_data['layer_height'] = value
                    obj_data['custom_settings']['layer_height'] = value
                elif key == 'wall_loops':
                    obj_data['wall_loops'] = value
                    obj_data['custom_settings']['wall_loops'] = value
                elif key in INFILL_DENSITY_KEYS:
                    if obj_data['sparse_infill_density'] is None:
                        obj_data['sparse_infill_density'] = value
                    obj_data['custom_settings'][key] = value
                elif key == 'enable_support':
                    obj_data['enable_support'] = value
                    obj_data['custom_settings']['enable_support'] = value
                elif key == 'brim_type':
                    obj_data['brim_type'] = value
                    obj_data['custom_settings']['brim_type'] = value
                elif key == 'outer_wall_speed':
                    obj_data['outer_wall_speed'] = value
                    obj_data['custom_settings']['outer_wall_speed'] = value
                elif key == 'inner_wall_speed':
                    obj_data['inner_wall_speed'] = value
                    obj_data['custom_settings']['inner_wall_speed'] = value
                elif key not in SYSTEM_KEYS and value is not None:
                    obj_data['custom_settings'][key] = value

            # Object parts
            for part in obj.findall('part'):
                part_data = {
                    'name': None,
                    'extruder': None,
                    'custom_settings': {},
                }
                for meta in part.findall('metadata'):
                    key = meta.get('key')
                    value = meta.get('value')
                    if key == 'name':
                        part_data['name'] = value
                    elif key == 'extruder':
                        part_data['extruder'] = value
                    elif key not in SYSTEM_KEYS and value is not None:
                        part_data['custom_settings'][key] = value
                obj_data['parts'].append(part_data)

            self.objects[obj_id] = obj_data

        # Parse plates
        for plate in root.findall('.//plate'):
            plate_id = None
            plate_name = None
            plate_objects = []

            for meta in plate.findall('metadata'):
                key = meta.get('key')
                value = meta.get('value')
                if key == 'plater_id':
                    plate_id = value
                elif key == 'plater_name':
                    plate_name = value

            for inst in plate.findall('model_instance'):
                obj_id = None
                identify_id = 0
                for meta in inst.findall('metadata'):
                    key = meta.get('key')
                    value = meta.get('value')
                    if key == 'object_id':
                        obj_id = value
                    elif key == 'identify_id':
                        try:
                            identify_id = int(value)
                        except (ValueError, TypeError):
                            logger.warning(
                                "Invalid identify_id value '%s', using default %d",
                                value, DEFAULT_IDENTIFY_ID,
                            )
                            identify_id = DEFAULT_IDENTIFY_ID
                if obj_id:
                    plate_objects.append({'object_id': obj_id, 'identify_id': identify_id})

            # Sort by identify_id ascending (matches slicer display order)
            plate_objects.sort(key=lambda x: x['identify_id'])

            if plate_id:
                self.plates.append({
                    'id': plate_id,
                    'name': plate_name,
                    'objects': [obj['object_id'] for obj in plate_objects]
                })

    def _get_value(self, key: str, default=None, index: int = 0):
        """Get value from project_settings.

        Args:
            key: Setting key to retrieve.
            default: Default value if key not found.
            index: Which element to return for list values.
                   0 = first element (default), -1 = entire list.

        Returns:
            The setting value, or default if not found.
        """
        val = self.project_settings.get(key, default)
        if isinstance(val, list):
            if index == -1:
                return val  # Return entire list
            if not val:  # Empty list
                return default
            return val[index] if 0 <= index < len(val) else default
        return val

    def _get_custom_global_settings(self) -> Dict[str, Any]:
        """Extract custom global settings."""
        custom = {}

        diff_settings = self.project_settings.get('different_settings_to_system', [])
        # Validate that diff_settings is a non-empty list before accessing first element
        if isinstance(diff_settings, list) and len(diff_settings) > 0 and diff_settings[0]:
            # Filter empty strings that result from split on empty or ";;"
            keys = [k.strip() for k in diff_settings[0].split(';') if k.strip()]
            for key in keys:
                if key in self.project_settings:
                    value = self.project_settings[key]
                    if isinstance(value, list) and len(value) == 1:
                        value = value[0]
                    custom[key] = value

        return custom

    def _get_profile_info(self) -> Dict[str, Any]:
        """Extract profile information."""
        profile = build_common_profile(self._get_value)
        profile['printer'] = self.project_settings.get('printer_settings_id', 'Unknown')
        profile['process'] = self.project_settings.get('print_settings_id', 'Unknown')
        profile['filaments'] = self.project_settings.get('filament_settings_id', ['Unknown'])
        profile['initial_layer_print_height'] = self._get_value('initial_layer_print_height', '')
        return profile

    def _format_brim(self, brim_type: str) -> str:
        if not brim_type:
            return ''
        mapping = {
            'brim_ears': 'Mouse ear',
            'no_brim': 'No',
            'outer_only': 'Outer',
            'inner_only': 'Inner',
            'outer_and_inner': 'Both'
        }
        return mapping.get(brim_type, brim_type)

    def _format_infill(self, value: Any) -> str:
        """Format infill density value, removing % sign if present."""
        if value is None:
            return ''
        return str(value).replace('%', '')

    def _build_object_row(
        self, 
        obj: Dict[str, Any], 
        obj_id: str, 
        plate_num: int, 
        profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build a row for a single object.
        
        Args:
            obj: Object data dictionary
            obj_id: Object ID
            plate_num: Plate number
            profile: Global profile settings
            
        Returns:
            Dictionary representing the object row
        """
        obj_name = obj.get('name', f'Object {obj_id}')
        
        obj_layer = obj.get('layer_height') or profile['layer_height']
        obj_walls = obj.get('wall_loops') or profile['wall_loops']
        obj_infill = obj.get('sparse_infill_density') or profile['sparse_infill_density']
        obj_support = obj.get('enable_support') or profile['enable_support']
        obj_brim = obj.get('brim_type') or profile['brim_type']
        obj_speed = obj.get('outer_wall_speed') or profile['outer_wall_speed']
        obj_extruder = obj.get('extruder', DEFAULT_EXTRUDER)
        
        return {
            'plate': plate_num,
            'name': obj_name,
            'is_parent': True,
            'is_part': False,
            'filament': obj_extruder,
            'layer_height': obj_layer,
            'layer_custom': _is_custom(obj.get('layer_height'), profile['layer_height']),
            'wall_loops': obj_walls,
            'walls_custom': _is_custom(obj.get('wall_loops'), profile['wall_loops']),
            'infill': self._format_infill(obj_infill),
            'infill_custom': _is_custom(obj.get('sparse_infill_density'), profile['sparse_infill_density']),
            'support': 'On' if obj_support == BOOL_TRUE else 'Off',
            'support_custom': _is_custom(obj.get('enable_support'), profile['enable_support']),
            'brim': self._format_brim(obj_brim),
            'brim_custom': _is_custom(obj.get('brim_type'), profile['brim_type']),
            'outer_wall_speed': obj_speed,
            'speed_custom': _is_custom(obj.get('outer_wall_speed'), profile['outer_wall_speed']),
            'custom_settings': obj.get('custom_settings', {}),
            # Store values for part inheritance
            '_obj_infill': obj_infill,
            '_obj_walls': obj_walls,
            '_obj_speed': obj_speed,
            '_obj_support': obj_support,
            '_obj_extruder': obj_extruder,
        }

    def _build_part_row(
        self, 
        part: Dict[str, Any], 
        parent_row: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build a row for a part (inherits values from parent object).
        
        Args:
            part: Part data dictionary
            parent_row: Parent object row (contains inherited values)
            
        Returns:
            Dictionary representing the part row
        """
        part_name = part.get('name', 'Part')
        part_custom = part.get('custom_settings', {})
        
        # Inherit from parent object
        obj_infill = parent_row['_obj_infill']
        obj_walls = parent_row['_obj_walls']
        obj_speed = parent_row['_obj_speed']
        obj_support = parent_row['_obj_support']
        obj_extruder = parent_row['_obj_extruder']
        
        part_extruder = part.get('extruder') or obj_extruder
        
        # Check for part-specific overrides (use part's custom value or inherit from parent)
        part_infill = (
            part_custom.get('sparse_infill_density')
            or part_custom.get('skeleton_infill_density')
            or obj_infill
        )
        part_infill_custom = any(k in part_custom for k in INFILL_DENSITY_KEYS)
        
        part_walls = part_custom.get('wall_loops') or obj_walls
        part_walls_custom = 'wall_loops' in part_custom
        
        part_speed = part_custom.get('outer_wall_speed') or obj_speed
        part_speed_custom = 'outer_wall_speed' in part_custom
        
        # Inherit support from parent
        part_support = 'On' if obj_support == BOOL_TRUE else 'Off'
        
        return {
            'plate': '',
            'name': f"  {part_name}",
            'is_parent': False,
            'is_part': True,
            'filament': part_extruder,
            'layer_height': '',
            'layer_custom': False,
            'wall_loops': part_walls,
            'walls_custom': part_walls_custom,
            'infill': self._format_infill(part_infill),
            'infill_custom': part_infill_custom,
            'support': part_support,
            'support_custom': False,
            'brim': '',
            'brim_custom': False,
            'outer_wall_speed': part_speed,
            'speed_custom': part_speed_custom,
            'custom_settings': part_custom,
        }

    def _build_result(self) -> Dict[str, Any]:
        """Build the result by aggregating all objects and parts from all plates."""
        profile = self._get_profile_info()
        rows = []

        for plate in self.plates:
            plate_num = plate['id']

            for obj_id in plate['objects']:
                obj = self.objects.get(obj_id, {})
                obj_name = obj.get('name', f'Object {obj_id}')
                
                # Build object row
                obj_row = self._build_object_row(obj, obj_id, plate_num, profile)
                rows.append(obj_row)

                # Process parts (inherit values from parent object like slicer does)
                # Skip parts if there's only one part with the same name as the object
                parts = obj.get('parts', [])
                if len(parts) == 1 and parts[0].get('name', 'Part') == obj_name:
                    continue  # Don't duplicate single part with same name as object

                for part in parts:
                    part_row = self._build_part_row(part, obj_row)
                    rows.append(part_row)

        # Clean up internal fields used for inheritance
        for row in rows:
            row.pop('_obj_infill', None)
            row.pop('_obj_walls', None)
            row.pop('_obj_speed', None)
            row.pop('_obj_support', None)
            row.pop('_obj_extruder', None)

        return {
            'file': str(self.filepath.name),
            'profile': profile,
            'profile_full': self.project_settings,
            'custom_global': self._get_custom_global_settings(),
            'rows': rows
        }
