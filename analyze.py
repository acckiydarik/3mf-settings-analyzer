#!/usr/bin/env python3
"""
3MF Settings Analyzer
Analyzes 3MF and Gcode files and displays slicer settings in a structured table format.
Supports Bambu Studio, OrcaSlicer, Snapmaker Orca, and other slicers using the same 3MF/Gcode metadata format.
"""

__version__ = "1.9.0"

import zipfile
import json
import tempfile
import shutil
import sys
import argparse
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Tuple, Union, Set

# Use defusedxml to prevent XXE attacks - required dependency
try:
    import defusedxml.ElementTree as ET
except ImportError:
    raise ImportError(
        "Required package 'defusedxml' is not installed. "
        "Install it with: pip install defusedxml"
    )

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from rich.markup import escape


# ═══════════════════════════════════════════════════════════════
# Logging Configuration
# ═══════════════════════════════════════════════════════════════

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════

# System metadata keys that are not custom print settings
SYSTEM_KEYS = frozenset({
    'name', 'matrix', 'extruder', 'face_count',
    'source_object_id', 'source_volume_id',
    'source_offset_x', 'source_offset_y', 'source_offset_z'
})

# Boolean string values used in 3MF configs
BOOL_TRUE = '1'
BOOL_FALSE = '0'

# Infill density setting keys (skeleton_infill_density is legacy alias)
INFILL_DENSITY_KEYS = ('sparse_infill_density', 'skeleton_infill_density')

# Filament colors by number for table display
FILAMENT_COLORS = ('cyan', 'magenta', 'green', 'yellow', 'blue', 'red')

# Plate colors - distinct from filament colors, all clearly visible on dark bg
PLATE_COLORS = (
    'bright_white', 'dark_orange', 'wheat1', 'orchid',
    'turquoise2', 'salmon1', 'chartreuse3', 'deep_sky_blue1',
    'medium_purple1', 'gold1',
)

# Default extruder number (first extruder)
DEFAULT_EXTRUDER = '1'

# Fallback for sorting when identify_id is missing or invalid
DEFAULT_IDENTIFY_ID = 0

# File extensions
FILE_EXTENSION_3MF = '.3mf'
FILE_EXTENSION_GCODE = '.gcode'

# Gcode block markers
GCODE_HEADER_START = '; HEADER_BLOCK_START'
GCODE_HEADER_END = '; HEADER_BLOCK_END'
GCODE_CONFIG_START = '; CONFIG_BLOCK_START'
GCODE_CONFIG_END = '; CONFIG_BLOCK_END'
GCODE_OBJECT_MARKER = '; printing object '


# ═══════════════════════════════════════════════════════════════
# Analyzer
# ═══════════════════════════════════════════════════════════════

def _is_custom(obj_val: Any, global_val: Any) -> bool:
    """Check if object value differs from global profile value."""
    if obj_val is None:
        return False
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
        self._extract()
        try:
            self._parse_project_settings()
            self._parse_model_settings()
            result = self._build_result()
            logger.debug("Successfully analyzed %d objects", len(self.objects))
            return result
        finally:
            self._cleanup()
    
    def _extract(self):
        """Extract 3MF archive with Zip Slip protection.
        
        Validates all paths in the archive to prevent path traversal attacks.
        Uses a temporary directory that will be cleaned up in _cleanup().
        
        Raises:
            ValueError: If archive contains unsafe paths (Zip Slip attack).
            zipfile.BadZipFile: If the file is not a valid ZIP archive.
            OSError: If extraction fails due to filesystem issues.
        """
        self.temp_dir = Path(tempfile.mkdtemp())
        try:
            with zipfile.ZipFile(self.filepath, 'r') as z:
                # Zip Slip protection: validate all paths before extraction
                for member in z.namelist():
                    member_path = Path(member)
                    # Check for absolute paths or path traversal
                    if member_path.is_absolute():
                        raise ValueError(f"Unsafe absolute path in archive: {member}")
                    # Resolve and check if path stays within temp_dir
                    target_path = (self.temp_dir / member).resolve()
                    if not target_path.is_relative_to(self.temp_dir.resolve()):
                        raise ValueError(f"Path traversal detected in archive: {member}")
                z.extractall(self.temp_dir)
        except zipfile.BadZipFile as e:
            self._cleanup_on_error()
            raise zipfile.BadZipFile(f"Invalid or corrupted 3MF file: {self.filepath}") from e
        except ValueError:
            # Re-raise security-related errors without wrapping
            self._cleanup_on_error()
            raise
        except OSError as e:
            self._cleanup_on_error()
            raise OSError(f"Failed to extract 3MF archive '{self.filepath}': {e}") from e
        except Exception as e:
            self._cleanup_on_error()
            raise RuntimeError(f"Unexpected error extracting '{self.filepath}'") from e
    
    def _cleanup_on_error(self):
        """Cleanup temp directory on extraction error."""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir = None
    
    def _cleanup(self):
        """Cleanup temporary files"""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        self.temp_dir = None
    
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
            logger.warning("Unexpected root element '%s' in model_settings.config, expected 'config'", root.tag)
        
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
                'custom_settings': {},  # All custom settings for the object
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
                    # Any other custom settings
                    obj_data['custom_settings'][key] = value
            
            # Object parts
            for part in obj.findall('part'):
                part_data = {
                    'name': None, 
                    'extruder': None,
                    'custom_settings': {},  # All custom settings for the part
                }
                for meta in part.findall('metadata'):
                    key = meta.get('key')
                    value = meta.get('value')
                    if key == 'name':
                        part_data['name'] = value
                    elif key == 'extruder':
                        part_data['extruder'] = value
                    elif key not in SYSTEM_KEYS and value is not None:
                        # All other settings are custom
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
                            logger.warning("Invalid identify_id value '%s', using default %d", value, DEFAULT_IDENTIFY_ID)
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
        """Extract custom global settings"""
        custom = {}
        
        diff_settings = self.project_settings.get('different_settings_to_system', [])
        if diff_settings and diff_settings[0]:
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
        """Extract profile information"""
        return {
            'printer': self.project_settings.get('printer_settings_id', 'Unknown'),
            'process': self.project_settings.get('print_settings_id', 'Unknown'),
            'filaments': self.project_settings.get('filament_settings_id', ['Unknown']),
            # Basic settings
            'layer_height': self._get_value('layer_height', ''),
            'initial_layer_print_height': self._get_value('initial_layer_print_height', ''),
            'nozzle': self._get_value('nozzle_diameter', ''),
            'line_width': self._get_value('line_width', ''),
            'wall_loops': self._get_value('wall_loops', ''),
            'sparse_infill_density': self._get_value('sparse_infill_density', ''),
            'brim_type': self._get_value('brim_type', ''),
            'enable_support': self._get_value('enable_support', ''),
            # Flow
            'print_flow_ratio': self._get_value('print_flow_ratio', ''),
            'filament_flow_ratio': self._get_value('filament_flow_ratio', ''),
            # Speeds
            'initial_layer_speed': self._get_value('initial_layer_speed', ''),
            'outer_wall_speed': self._get_value('outer_wall_speed', ''),
            'inner_wall_speed': self._get_value('inner_wall_speed', ''),
            'sparse_infill_speed': self._get_value('sparse_infill_speed', ''),
            'top_surface_speed': self._get_value('top_surface_speed', ''),
            'travel_speed': self._get_value('travel_speed', ''),
            'bridge_speed': self._get_value('bridge_speed', ''),
            # Shells
            'top_shell_layers': self._get_value('top_shell_layers', ''),
            'bottom_shell_layers': self._get_value('bottom_shell_layers', ''),
            # Seams
            'seam_position': self._get_value('seam_position', ''),
            # === Extended settings ===
            # Patterns
            'sparse_infill_pattern': self._get_value('sparse_infill_pattern', ''),
            'top_surface_pattern': self._get_value('top_surface_pattern', ''),
            # Special modes
            'ironing_type': self._get_value('ironing_type', ''),
            'fuzzy_skin': self._get_value('fuzzy_skin', ''),
            'spiral_mode': self._get_value('spiral_mode', ''),
            # Retraction and Z
            'retraction_length': self._get_value('retraction_length', ''),
            'retraction_speed': self._get_value('retraction_speed', ''),
            'z_hop': self._get_value('z_hop', ''),
            # Fan
            'fan_min_speed': self._get_value('fan_min_speed', ''),
            'fan_max_speed': self._get_value('fan_max_speed', ''),
            # Cooling
            'slow_down_for_layer_cooling': self._get_value('slow_down_for_layer_cooling', ''),
            'slow_down_layer_time': self._get_value('slow_down_layer_time', ''),
            # Advanced
            'pressure_advance': self._get_value('pressure_advance', ''),
            'enable_arc_fitting': self._get_value('enable_arc_fitting', ''),
            'enable_overhang_speed': self._get_value('enable_overhang_speed', ''),
            # Print modes
            'print_sequence': self._get_value('print_sequence', ''),
            'timelapse_type': self._get_value('timelapse_type', ''),
            # Supports
            'support_type': self._get_value('support_type', ''),
            # Temperatures
            'nozzle_temperature': self._get_value('nozzle_temperature', ''),
            'bed_temperature': self._get_value('hot_plate_temp', ''),
        }
    
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
    
    def _build_result(self) -> Dict[str, Any]:
        """Build the result"""
        profile = self._get_profile_info()
        
        rows = []
        
        for plate in self.plates:
            plate_num = plate['id']
            
            for obj_id in plate['objects']:
                obj = self.objects.get(obj_id, {})
                obj_name = obj.get('name', f'Object {obj_id}')
                
                obj_layer = obj.get('layer_height') or profile['layer_height']
                obj_walls = obj.get('wall_loops') or profile['wall_loops']
                obj_infill = obj.get('sparse_infill_density') or profile['sparse_infill_density']
                obj_support = obj.get('enable_support') or profile['enable_support']
                obj_brim = obj.get('brim_type') or profile['brim_type']
                obj_speed = obj.get('outer_wall_speed') or profile['outer_wall_speed']
                obj_extruder = obj.get('extruder', DEFAULT_EXTRUDER)
                
                rows.append({
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
                })
                
                # Parts (inherit values from parent object like slicer does)
                # Skip parts if there's only one part with the same name as the object
                parts = obj.get('parts', [])
                if len(parts) == 1 and parts[0].get('name', 'Part') == obj_name:
                    continue  # Don't duplicate single part with same name as object
                    
                for part in parts:
                    part_name = part.get('name', 'Part')
                    part_extruder = part.get('extruder') or obj_extruder
                    part_custom = part.get('custom_settings', {})
                    
                    # Check for part-specific overrides (use part's custom value or inherit from parent)
                    part_infill = part_custom.get('sparse_infill_density') or part_custom.get('skeleton_infill_density') or obj_infill
                    part_infill_custom = any(k in part_custom for k in INFILL_DENSITY_KEYS)
                    
                    part_walls = part_custom.get('wall_loops') or obj_walls
                    part_walls_custom = 'wall_loops' in part_custom
                    
                    part_speed = part_custom.get('outer_wall_speed') or obj_speed
                    part_speed_custom = 'outer_wall_speed' in part_custom
                    
                    # Inherit support from parent
                    part_support = 'On' if obj_support == BOOL_TRUE else 'Off'
                    
                    rows.append({
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
                    })
        
        return {
            'file': str(self.filepath.name),
            'profile': profile,
            'profile_full': self.project_settings,
            'custom_global': self._get_custom_global_settings(),
            'rows': rows
        }


class GcodeAnalyzer:
    """Analyzes Gcode files and extracts slicer settings and statistics.
    
    Parses gcode files generated by OrcaSlicer, Bambu Studio, Snapmaker Orca,
    and other compatible slicers. Uses block markers for efficient parsing.
    """
    
    def __init__(self, filepath: Union[str, Path]):
        self.filepath = Path(filepath)
        self.settings: Dict[str, str] = {}
        self.header_info: Dict[str, str] = {}
        self.statistics: Dict[str, Any] = {}
        self.object_names: Set[str] = set()
    
    def analyze(self) -> Dict[str, Any]:
        """Main analysis method. Extracts settings and statistics from gcode file.
        
        Returns:
            Dict containing profile, settings, statistics, and object names.
            
        Raises:
            OSError: If the file cannot be read.
        """
        logger.debug("Starting gcode analysis of file: %s", self.filepath)
        
        if not self.filepath.exists():
            raise OSError(f"File not found: {self.filepath}")
        
        self._parse_gcode()
        result = self._build_result()
        logger.debug("Successfully analyzed gcode file")
        return result
    
    def _parse_gcode(self):
        """Parse gcode file using block markers for efficient parsing."""
        file_size = os.path.getsize(self.filepath)
        
        # Read file in chunks from the end to find CONFIG_BLOCK
        # Most gcode files have settings at the end
        with open(self.filepath, 'r', encoding='utf-8', errors='replace') as f:
            # First, read header (first 100 lines)
            header_lines = []
            for i, line in enumerate(f):
                if i >= 100:
                    break
                header_lines.append(line)
                if line.strip() == GCODE_HEADER_END:
                    break
            
            self._parse_header(header_lines)
            
            # Reset and scan for object markers (scan entire file for this)
            f.seek(0)
            for line in f:
                if line.startswith(GCODE_OBJECT_MARKER):
                    self._extract_object_name(line)
            
            # Now find and parse CONFIG_BLOCK from end of file
            # Read last portion of file (settings are typically in last ~50KB)
            f.seek(0, 2)  # Go to end
            file_end = f.tell()
            read_size = min(100000, file_end)  # Read up to 100KB from end
            f.seek(max(0, file_end - read_size))
            
            tail_content = f.read()
            self._parse_config_block(tail_content)
            self._parse_statistics(tail_content)
        
        # Add file size to statistics
        self.statistics['file_size_bytes'] = file_size
    
    def _parse_header(self, lines: List[str]):
        """Parse header block for basic info.
        
        Header format:
        ; generated by Snapmaker Orca 2.2.1 on 2026-01-30 at 12:34:13
        ; total layer number: 138
        ; max_z_height: 22.12
        """
        for line in lines:
            line = line.strip()
            if not line.startswith(';'):
                continue
            
            content = line[1:].strip()
            
            # Parse "generated by" line
            if content.startswith('generated by '):
                match = re.match(
                    r'generated by (.+?) (\d+\.\d+\.\d+) on (\d{4}-\d{2}-\d{2}) at (\d{2}:\d{2}:\d{2})',
                    content
                )
                if match:
                    self.header_info['slicer'] = match.group(1)
                    self.header_info['slicer_version'] = match.group(2)
                    self.header_info['generated_date'] = f"{match.group(3)} {match.group(4)}"
            
            # Parse key: value pairs in header
            elif ':' in content and '=' not in content:
                key, _, value = content.partition(':')
                key = key.strip().lower().replace(' ', '_')
                value = value.strip()
                self.header_info[key] = value
    
    def _extract_object_name(self, line: str):
        """Extract object name from '; printing object NAME id:XXX' marker."""
        # Format: ; printing object NAME id:123456 copy N
        content = line[len(GCODE_OBJECT_MARKER):].strip()
        # Remove id:xxx and copy N parts
        match = re.match(r'(.+?)\s+id:\d+', content)
        if match:
            obj_name = match.group(1).strip()
            self.object_names.add(obj_name)
    
    def _parse_config_block(self, content: str):
        """Parse CONFIG_BLOCK section for all settings.
        
        Settings format:
        ; setting_key = value
        """
        in_config = False
        
        for line in content.split('\n'):
            line = line.strip()
            
            if line == GCODE_CONFIG_START:
                in_config = True
                continue
            elif line == GCODE_CONFIG_END:
                break
            
            if in_config and line.startswith('; ') and ' = ' in line:
                # Parse setting line: ; key = value
                setting_line = line[2:]  # Remove "; "
                key, _, value = setting_line.partition(' = ')
                key = key.strip()
                value = value.strip()
                self.settings[key] = value
    
    def _parse_statistics(self, content: str):
        """Parse statistics from gcode (before CONFIG_BLOCK).
        
        Statistics format:
        ; filament used [g] = 10.08, 0.87, 0.31
        ; total filament used [g] = 11.26
        ; estimated printing time (normal mode) = 1h 11m 17s
        """
        # Statistics patterns (these appear before CONFIG_BLOCK)
        patterns = {
            'filament_used_g': r'^; filament used \[g\] = (.+)$',
            'filament_used_mm': r'^; filament used \[mm\] = (.+)$',
            'filament_used_cm3': r'^; filament used \[cm3\] = (.+)$',
            'filament_cost_per_extruder': r'^; filament cost = (.+)$',
            'total_filament_used_g': r'^; total filament used \[g\] = (.+)$',
            'total_filament_cost': r'^; total filament cost = (.+)$',
            'total_filament_change': r'^; total filament change = (\d+)$',
            'total_layers_count': r'^; total layers count = (\d+)$',
            'estimated_time': r'^; estimated printing time \(normal mode\) = (.+)$',
            'estimated_first_layer_time': r'^; estimated first layer printing time \(normal mode\) = (.+)$',
        }
        
        for line in content.split('\n'):
            line = line.strip()
            for key, pattern in patterns.items():
                match = re.match(pattern, line)
                if match:
                    value = match.group(1).strip()
                    # Parse numeric values
                    if key in ('total_filament_used_g', 'total_filament_cost'):
                        try:
                            self.statistics[key] = float(value)
                        except ValueError:
                            self.statistics[key] = value
                    elif key in ('total_filament_change', 'total_layers_count'):
                        try:
                            self.statistics[key] = int(value)
                        except ValueError:
                            self.statistics[key] = value
                    elif key in ('filament_used_g', 'filament_used_mm', 'filament_used_cm3',
                                  'filament_cost_per_extruder'):
                        # Parse comma-separated list of floats
                        try:
                            self.statistics[key] = [float(v.strip()) for v in value.split(',')]
                        except ValueError:
                            self.statistics[key] = value
                    else:
                        self.statistics[key] = value
                    break
    
    def _get_value(self, key: str, default: Any = None) -> Any:
        """Get value from settings, handling list formats.
        
        Gcode settings often have comma-separated values for multi-extruder setups.
        This method returns the first value for such settings.
        """
        value = self.settings.get(key, default)
        if value is None:
            return default
        
        # Handle semicolon-separated list (filament names)
        if ';' in str(value):
            parts = [p.strip().strip('"') for p in str(value).split(';') if p.strip()]
            return parts[0] if parts else default
        
        # Handle comma-separated list (numeric values)
        if ',' in str(value):
            parts = [p.strip() for p in str(value).split(',') if p.strip()]
            return parts[0] if parts else default
        
        return value
    
    def _get_list_value(self, key: str, default: Any = None) -> List[str]:
        """Get list value from settings."""
        value = self.settings.get(key)
        if value is None:
            return default if default is not None else []
        
        # Handle semicolon-separated list (filament names)
        if ';' in str(value):
            return [p.strip().strip('"') for p in str(value).split(';') if p.strip()]
        
        # Handle comma-separated list
        if ',' in str(value):
            return [p.strip() for p in str(value).split(',') if p.strip()]
        
        return [str(value)]
    
    def _get_custom_global_settings(self) -> Dict[str, Any]:
        """Extract custom global settings from different_settings_to_system."""
        custom = {}
        
        diff_settings = self.settings.get('different_settings_to_system', '')
        if diff_settings:
            keys = [k.strip() for k in diff_settings.split(';') if k.strip()]
            for key in keys:
                if key in self.settings:
                    custom[key] = self.settings[key]
        
        return custom
    
    def _get_profile_info(self) -> Dict[str, Any]:
        """Extract profile information matching ThreeMFAnalyzer format."""
        return {
            'printer': self.settings.get('printer_settings_id', 'Unknown'),
            'process': self.settings.get('print_settings_id', 'Unknown'),
            'filaments': self._get_list_value('filament_settings_id', ['Unknown']),
            # Basic settings
            'layer_height': self._get_value('layer_height', ''),
            'initial_layer_print_height': self._get_value('first_layer_height', ''),
            'nozzle': self._get_value('nozzle_diameter', ''),
            'line_width': self._get_value('line_width', ''),
            'wall_loops': self._get_value('wall_loops', ''),
            'sparse_infill_density': self._get_value('sparse_infill_density', ''),
            'brim_type': self._get_value('brim_type', ''),
            'enable_support': self._get_value('enable_support', ''),
            # Flow
            'print_flow_ratio': self._get_value('print_flow_ratio', ''),
            'filament_flow_ratio': self._get_value('filament_flow_ratio', ''),
            # Speeds
            'initial_layer_speed': self._get_value('initial_layer_speed', ''),
            'outer_wall_speed': self._get_value('outer_wall_speed', ''),
            'inner_wall_speed': self._get_value('inner_wall_speed', ''),
            'sparse_infill_speed': self._get_value('sparse_infill_speed', ''),
            'top_surface_speed': self._get_value('top_surface_speed', ''),
            'travel_speed': self._get_value('travel_speed', ''),
            'bridge_speed': self._get_value('bridge_speed', ''),
            # Shells
            'top_shell_layers': self._get_value('top_shell_layers', ''),
            'bottom_shell_layers': self._get_value('bottom_shell_layers', ''),
            # Seams
            'seam_position': self._get_value('seam_position', ''),
            # Patterns
            'sparse_infill_pattern': self._get_value('sparse_infill_pattern', ''),
            'top_surface_pattern': self._get_value('top_surface_pattern', ''),
            # Special modes
            'ironing_type': self._get_value('ironing_type', ''),
            'fuzzy_skin': self._get_value('fuzzy_skin', ''),
            'spiral_mode': self._get_value('spiral_mode', ''),
            # Retraction and Z
            'retraction_length': self._get_value('retraction_length', ''),
            'retraction_speed': self._get_value('retraction_speed', ''),
            'z_hop': self._get_value('z_hop', ''),
            # Fan
            'fan_min_speed': self._get_value('fan_min_speed', ''),
            'fan_max_speed': self._get_value('fan_max_speed', ''),
            # Cooling
            'slow_down_for_layer_cooling': self._get_value('slow_down_for_layer_cooling', ''),
            'slow_down_layer_time': self._get_value('slow_down_layer_time', ''),
            # Advanced
            'pressure_advance': self._get_value('pressure_advance', ''),
            'enable_arc_fitting': self._get_value('enable_arc_fitting', ''),
            'enable_overhang_speed': self._get_value('enable_overhang_speed', ''),
            # Print modes
            'print_sequence': self._get_value('print_sequence', ''),
            'timelapse_type': self._get_value('timelapse_type', ''),
            # Supports
            'support_type': self._get_value('support_type', ''),
            # Temperatures
            'nozzle_temperature': self._get_value('nozzle_temperature', ''),
            'bed_temperature': self._get_value('hot_plate_temp', ''),
        }
    
    def _build_statistics(self) -> Dict[str, Any]:
        """Build comprehensive statistics dictionary."""
        stats = {}
        
        # Slicer info from header
        stats['slicer'] = self.header_info.get('slicer', '')
        stats['slicer_version'] = self.header_info.get('slicer_version', '')
        stats['generated_date'] = self.header_info.get('generated_date', '')
        
        # Time estimates
        stats['estimated_time'] = self.statistics.get('estimated_time', '')
        stats['estimated_first_layer_time'] = self.statistics.get('estimated_first_layer_time', '')
        
        # Layer info
        try:
            stats['total_layers'] = (
                self.statistics.get('total_layers_count')
                or int(self.header_info.get('total_layer_number', 0) or 0)
            )
        except (ValueError, TypeError):
            stats['total_layers'] = 0
        try:
            stats['max_height'] = float(self.header_info.get('max_z_height', 0) or 0)
        except (ValueError, TypeError):
            stats['max_height'] = 0.0
        stats['layer_height'] = self._get_value('layer_height', '')
        stats['first_layer_height'] = self._get_value('first_layer_height', '')
        
        # Nozzle
        stats['nozzle_diameter'] = self._get_list_value('nozzle_diameter', [])
        
        # Filament usage
        stats['filament_used_g'] = self.statistics.get('total_filament_used_g', 0)
        stats['filament_used_per_extruder_g'] = self.statistics.get('filament_used_g', [])
        stats['filament_used_per_extruder_mm'] = self.statistics.get('filament_used_mm', [])
        stats['filament_cost'] = self.statistics.get('total_filament_cost', 0)
        stats['filament_cost_per_extruder'] = self.statistics.get('filament_cost_per_extruder', [])
        stats['filament_changes'] = self.statistics.get('total_filament_change', 0)
        
        # Filament info
        stats['filament_names'] = self._get_list_value('filament_settings_id', [])
        stats['filament_types'] = self._get_list_value('filament_type', [])
        stats['filament_colors'] = self._get_list_value('filament_colour', [])
        stats['filament_density'] = self._get_list_value('filament_density', [])
        stats['filament_diameter'] = self._get_list_value('filament_diameter', [])
        
        # Temperatures
        stats['first_layer_bed_temp'] = self._get_value('first_layer_bed_temperature', '') or \
                                         self._get_value('hot_plate_temp_initial_layer', '')
        stats['first_layer_nozzle_temp'] = self._get_value('first_layer_temperature', '') or \
                                            self._get_value('nozzle_temperature_initial_layer', '')
        stats['nozzle_temp'] = self._get_list_value('nozzle_temperature', [])
        stats['bed_temp'] = self._get_value('hot_plate_temp', '') or \
                            self._get_value('bed_temperature', '')
        
        # Printer/Machine info
        stats['printer_model'] = self._get_value('printer_model', '')
        stats['gcode_flavor'] = self._get_value('gcode_flavor', '')
        stats['nozzle_type'] = self._get_value('nozzle_type', '')
        stats['curr_bed_type'] = self._get_value('curr_bed_type', '')
        
        # Filament extra
        stats['filament_vendor'] = self._get_list_value('filament_vendor', [])
        stats['filament_used_per_extruder_cm3'] = self.statistics.get('filament_used_cm3', [])
        stats['enable_prime_tower'] = self._get_value('enable_prime_tower', '')
        
        # File size
        stats['file_size_bytes'] = self.statistics.get('file_size_bytes', 0)
        
        return stats
    
    def _build_result(self) -> Dict[str, Any]:
        """Build the result dictionary."""
        return {
            'file': str(self.filepath.name),
            'profile': self._get_profile_info(),
            'profile_full': self.settings,
            'custom_global': self._get_custom_global_settings(),
            'rows': [],  # Gcode doesn't have per-object settings
            'objects': sorted(self.object_names),  # Object names list
            'statistics': self._build_statistics(),
        }


# ═══════════════════════════════════════════════════════════════
# Output
# ═══════════════════════════════════════════════════════════════

def _make_wiki_helpers(enabled: bool) -> Tuple[Callable[[str, str], str], Callable[[str], str]]:
    """Create wiki_label and wiki_key helpers based on --wiki flag.

    When disabled, returns no-op passthrough functions to avoid
    importing settings_wiki module entirely.
    
    Returns:
        Tuple of (wiki_label, wiki_key) callable functions.
    """
    if not enabled:
        return (
            lambda display_name, setting_key: display_name,
            lambda setting_key: setting_key,
        )

    try:
        from settings_wiki import get_wiki_url
    except ImportError as e:
        logger.warning("Wiki module unavailable: %s. Wiki links disabled.", e)
        return (
            lambda display_name, setting_key: display_name,
            lambda setting_key: setting_key,
        )
    from rich.markup import escape

    def wiki_label(display_name: str, setting_key: str) -> str:
        """Wrap display_name in a Rich hyperlink to the OrcaSlicer wiki page."""
        url = get_wiki_url(setting_key)
        safe_name = escape(display_name)
        if url:
            return f"[link={url}]{safe_name}[/link]"
        return safe_name

    def wiki_key(setting_key: str) -> str:
        """Wrap a raw setting key in a Rich hyperlink to the wiki page."""
        url = get_wiki_url(setting_key)
        safe_key = escape(setting_key)
        if url:
            return f"[link={url}]{safe_key}[/link]"
        return safe_key

    return wiki_label, wiki_key


def _print_header(console: Console, filename: str):
    console.print(Panel(f"[bold cyan]3MF SETTINGS ANALYZER[/bold cyan]  │  {filename}", 
                        border_style="cyan"))


def _print_profile_panel(console: Console, profile: Dict[str, Any]):
    profile_table = Table(show_header=False, box=None, padding=(0, 2))
    profile_table.add_column("Key", style="dim")
    profile_table.add_column("Value")
    
    profile_table.add_row("Printer", f"[white]{profile['printer']}[/white]")
    profile_table.add_row("Process", f"[green]{profile['process']}[/green]")
    
    filaments = profile['filaments']
    if isinstance(filaments, list):
        for i, f in enumerate(filaments):
            profile_table.add_row(f"Filament {i+1}", f"[magenta]{f}[/magenta]")
    
    console.print(Panel(profile_table, title="[bold bright_yellow]PROFILE[/bold bright_yellow]",
                        border_style="grey50", box=box.ROUNDED))


def _print_global_settings(console: Console, profile: Dict[str, Any], wiki_label):
    gs = Table(show_header=False, box=None, padding=(0, 2))
    gs.add_column("Key", style="dim")
    gs.add_column("Value", style="white")
    
    # -- Basic --
    gs.add_row(wiki_label("Layer Height", "layer_height"), f"{profile['layer_height']} mm")
    if profile['initial_layer_print_height']:
        gs.add_row(wiki_label("Initial Layer Print Height", "initial_layer_print_height"), f"{profile['initial_layer_print_height']} mm")
    if profile['line_width']:
        gs.add_row(wiki_label("Line Width", "line_width"), f"{profile['line_width']} mm")
    if profile['print_flow_ratio'] and profile['print_flow_ratio'] != '1':
        try:
            flow_pct = f"{float(profile['print_flow_ratio']) * 100:.0f}%"
        except (ValueError, TypeError):
            flow_pct = str(profile['print_flow_ratio'])
        gs.add_row(wiki_label("Print Flow Ratio", "print_flow_ratio"), flow_pct)
    elif profile['filament_flow_ratio']:
        gs.add_row(wiki_label("Filament Flow Ratio", "filament_flow_ratio"), profile['filament_flow_ratio'])
    gs.add_row(wiki_label("Wall Loops", "wall_loops"), profile['wall_loops'])
    gs.add_row(wiki_label("Sparse Infill Density", "sparse_infill_density"), profile['sparse_infill_density'])
    gs.add_row(wiki_label("Top/Bottom Shell Layers", "top_shell_layers"), f"{profile['top_shell_layers']}/{profile['bottom_shell_layers']}")
    gs.add_row(wiki_label("Brim Type", "brim_type"), profile['brim_type'])
    gs.add_row(wiki_label("Enable Support", "enable_support"), "On" if profile['enable_support'] == BOOL_TRUE else "Off")
    gs.add_row(wiki_label("Seam Position", "seam_position"), profile['seam_position'])
    
    # -- Speeds --
    gs.add_row("", "")
    if profile['initial_layer_speed']:
        gs.add_row(wiki_label("Initial Layer Speed", "initial_layer_speed"), f"[cyan]{profile['initial_layer_speed']} mm/s[/cyan]")
    gs.add_row(wiki_label("Outer Wall Speed", "outer_wall_speed"), f"[cyan]{profile['outer_wall_speed']} mm/s[/cyan]")
    gs.add_row(wiki_label("Inner Wall Speed", "inner_wall_speed"), f"[cyan]{profile['inner_wall_speed']} mm/s[/cyan]")
    if profile['sparse_infill_speed']:
        gs.add_row(wiki_label("Sparse Infill Speed", "sparse_infill_speed"), f"[cyan]{profile['sparse_infill_speed']} mm/s[/cyan]")
    if profile['top_surface_speed']:
        gs.add_row(wiki_label("Top Surface Speed", "top_surface_speed"), f"[cyan]{profile['top_surface_speed']} mm/s[/cyan]")
    gs.add_row(wiki_label("Travel Speed", "travel_speed"), f"[cyan]{profile['travel_speed']} mm/s[/cyan]")
    gs.add_row(wiki_label("Bridge Speed", "bridge_speed"), f"[cyan]{profile['bridge_speed']} mm/s[/cyan]")
    
    # -- Patterns --
    gs.add_row("", "")
    gs.add_row(wiki_label("Sparse Infill Pattern", "sparse_infill_pattern"), profile['sparse_infill_pattern'])
    gs.add_row(wiki_label("Top Surface Pattern", "top_surface_pattern"), profile['top_surface_pattern'])
    gs.add_row(wiki_label("Print Sequence", "print_sequence"), profile['print_sequence'])
    if profile['spiral_mode'] == BOOL_TRUE:
        gs.add_row(wiki_label("Spiral Mode (Vase)", "spiral_mode"), "[bright_green]ON[/bright_green]")
    if profile['ironing_type'] and profile['ironing_type'] not in ('no ironing', 'no_ironing'):
        gs.add_row(wiki_label("Ironing Type", "ironing_type"), f"[bright_green]{profile['ironing_type']}[/bright_green]")
    if profile['fuzzy_skin'] and profile['fuzzy_skin'] != 'none':
        gs.add_row(wiki_label("Fuzzy Skin", "fuzzy_skin"), f"[bright_green]{profile['fuzzy_skin']}[/bright_green]")
    
    # -- Retraction / Z-hop / PA / Fan / Cooling --
    gs.add_row("", "")
    gs.add_row(wiki_label("Retraction Length", "retraction_length"), f"{profile['retraction_length']} mm")
    if profile['retraction_speed']:
        gs.add_row(wiki_label("Retraction Speed", "retraction_speed"), f"{profile['retraction_speed']} mm/s")
    gs.add_row(wiki_label("Z-Hop", "z_hop"), f"{profile['z_hop']} mm")
    if profile['pressure_advance']:
        gs.add_row(wiki_label("Pressure Advance", "pressure_advance"), profile['pressure_advance'])
    if profile['fan_min_speed'] or profile['fan_max_speed']:
        gs.add_row(wiki_label("Fan Min/Max Speed", "fan_min_speed"), f"{profile['fan_min_speed']}% / {profile['fan_max_speed']}%")
    if profile['slow_down_for_layer_cooling'] == BOOL_TRUE:
        gs.add_row(wiki_label("Slow Down for Layer Cooling", "slow_down_for_layer_cooling"), f"[green]On[/green] ({profile['slow_down_layer_time']}s)")
    elif profile['slow_down_for_layer_cooling']:
        gs.add_row(wiki_label("Slow Down for Layer Cooling", "slow_down_for_layer_cooling"), "[dim]Off[/dim]")
    
    # -- Temperatures --
    gs.add_row("", "")
    gs.add_row(wiki_label("Nozzle Temperature", "nozzle_temperature"), f"[red]{profile['nozzle_temperature']}°C[/red]")
    if profile['bed_temperature']:
        gs.add_row(wiki_label("Bed Temperature", "bed_temperature"), f"[red]{profile['bed_temperature']}°C[/red]")
    
    # -- Features --
    flags = []
    if profile['enable_arc_fitting'] == BOOL_TRUE:
        flags.append('Enable Arc Fitting')
    if profile['enable_overhang_speed'] == BOOL_TRUE:
        flags.append('Enable Overhang Speed')
    if profile['timelapse_type'] and profile['timelapse_type'] != '0':
        flags.append(f"Timelapse Type: {profile['timelapse_type']}")
    if flags:
        gs.add_row("", "")
        gs.add_row("[dim]Features[/dim]", f"[bright_cyan]{', '.join(flags)}[/bright_cyan]")
    
    console.print(Panel(gs, title="[bold bright_yellow]GLOBAL SETTINGS[/bold bright_yellow]",
                        border_style="grey50", box=box.ROUNDED))


def _print_custom_global(console: Console, custom: Dict[str, Any], wiki_key):
    if not custom:
        return
    custom_table = Table(show_header=False, box=None, padding=(0, 2))
    custom_table.add_column("Key", style="yellow")
    custom_table.add_column("Value", style="white")
    for k, v in custom.items():
        custom_table.add_row(f"* {wiki_key(k)}", escape(str(v)))
    console.print(Panel(custom_table,
                        title="[bold bright_red]CUSTOM GLOBAL SETTINGS[/bold bright_red] [grey50](changed from profile)[/grey50]",
                        border_style="grey50", box=box.ROUNDED))


def _format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


def _hex_to_color_name(hex_color: str) -> Tuple[str, str]:
    """Convert hex color (#RRGGBBAA or #RRGGBB) to approximate color name and Rich style.
    
    Args:
        hex_color: Hex color string like '#DE1619FF' or '#DE1619'
        
    Returns:
        Tuple of (color_name, rich_style) for terminal display.
        rich_style is a Rich color name for styling the output.
    """
    if not hex_color or not hex_color.startswith('#'):
        return (hex_color, 'white')
    
    try:
        # Remove # and handle both #RRGGBB and #RRGGBBAA formats
        hex_str = hex_color[1:]
        if len(hex_str) >= 6:
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
        else:
            return (hex_color, 'white')
        
        # Simple color classification based on RGB values
        # Check for grayscale first
        if abs(r - g) < 30 and abs(g - b) < 30 and abs(r - b) < 30:
            avg = (r + g + b) // 3
            if avg < 40:
                return ('Black', 'grey23')
            elif avg < 100:
                return ('Dark Gray', 'grey50')
            elif avg < 180:
                return ('Gray', 'grey70')
            elif avg < 230:
                return ('Light Gray', 'grey85')
            else:
                return ('White', 'bright_white')
        
        # Determine dominant color(s)
        max_val = max(r, g, b)
        
        # High saturation colors
        if max_val > 150:
            if r == max_val and g < 100 and b < 100:
                return ('Red', 'red')
            elif g == max_val and r < 100 and b < 100:
                return ('Green', 'green')
            elif b == max_val and r < 100 and g < 100:
                return ('Blue', 'blue')
            elif r > 200 and g > 200 and b < 100:
                return ('Yellow', 'yellow')
            elif r > 200 and b > 150 and g < 100:
                return ('Magenta', 'magenta')
            elif g > 200 and b > 200 and r < 100:
                return ('Cyan', 'cyan')
            elif r > 200 and g > 100 and g < 180 and b < 100:
                return ('Orange', 'dark_orange')
            elif r > 150 and b > 150 and g < 100:
                return ('Purple', 'purple')
            elif r > 150 and g > 100 and b > 80 and b < 150:
                return ('Brown', 'orange4')
            elif r > 200 and g > 150 and b > 150:
                return ('Pink', 'hot_pink')
        
        # Fallback: return hex code
        return (hex_color, 'white')
        
    except (ValueError, IndexError):
        return (hex_color, 'white')


def _format_filament_list(values: List[Any], suffix: str = '') -> str:
    """Format list of filament values (per extruder)."""
    if not values:
        return ''
    if len(values) == 1:
        return f"{values[0]}{suffix}"
    return ', '.join(f"{v}{suffix}" for v in values)


def _print_statistics_panel(console: Console, statistics: Dict[str, Any]):
    """Print statistics panel for gcode analysis results."""
    if not statistics:
        return
    
    stats_table = Table(show_header=False, box=None, padding=(0, 2))
    stats_table.add_column("Key", style="dim")
    stats_table.add_column("Value", style="white")
    
    # Slicer info and file
    if statistics.get('slicer'):
        slicer_info = statistics['slicer']
        if statistics.get('slicer_version'):
            slicer_info += f" {statistics['slicer_version']}"
        stats_table.add_row("Slicer", f"[cyan]{slicer_info}[/cyan]")
    
    if statistics.get('generated_date'):
        stats_table.add_row("Generated", statistics['generated_date'])
    
    if statistics.get('file_size_bytes'):
        stats_table.add_row("File Size", _format_file_size(statistics['file_size_bytes']))
    
    if statistics.get('printer_model'):
        stats_table.add_row("Printer Model", statistics['printer_model'])
    
    if statistics.get('gcode_flavor'):
        stats_table.add_row("G-code Flavor", statistics['gcode_flavor'])
    
    if statistics.get('nozzle_type'):
        stats_table.add_row("Nozzle Type", statistics['nozzle_type'])
    
    if statistics.get('curr_bed_type'):
        stats_table.add_row("Bed Type", statistics['curr_bed_type'])
    
    # Time estimates
    stats_table.add_row("", "")  # Separator
    
    if statistics.get('estimated_time'):
        stats_table.add_row("Estimated Time", f"[green]{statistics['estimated_time']}[/green]")
    
    if statistics.get('estimated_first_layer_time'):
        stats_table.add_row("First Layer Time", statistics['estimated_first_layer_time'])
    
    # Layer info
    stats_table.add_row("", "")  # Separator
    
    if statistics.get('total_layers'):
        stats_table.add_row("Total Layers", str(statistics['total_layers']))
    
    if statistics.get('max_height'):
        stats_table.add_row("Max Height", f"{statistics['max_height']} mm")
    
    if statistics.get('layer_height'):
        stats_table.add_row("Layer Height", f"{statistics['layer_height']} mm")
    
    if statistics.get('first_layer_height'):
        stats_table.add_row("First Layer Height", f"{statistics['first_layer_height']} mm")
    
    # Nozzle
    if statistics.get('nozzle_diameter'):
        nozzles = statistics['nozzle_diameter']
        if isinstance(nozzles, list) and nozzles:
            stats_table.add_row("Nozzle Diameter", f"{nozzles[0]} mm")
    
    # Filament usage -- grouped: weight, volume, cost
    stats_table.add_row("", "")  # Separator
    
    if statistics.get('filament_used_g'):
        stats_table.add_row("Filament Weight (Total)", f"[magenta]{statistics['filament_used_g']:.2f} g[/magenta]")
    
    if statistics.get('filament_used_per_extruder_g'):
        per_ext = _format_filament_list(
            [f"{v:.2f}" for v in statistics['filament_used_per_extruder_g']], 
            ' g'
        )
        if per_ext:
            stats_table.add_row("Filament Weight Per Extruder", per_ext)
    
    if statistics.get('filament_used_per_extruder_cm3'):
        per_ext_cm3 = _format_filament_list(
            [f"{v:.2f}" for v in statistics['filament_used_per_extruder_cm3']],
            ' cm3'
        )
        if per_ext_cm3:
            stats_table.add_row("Filament Volume Per Extruder", per_ext_cm3)
    
    if statistics.get('filament_cost') and statistics['filament_cost'] > 0:
        stats_table.add_row("Filament Cost (Total)", f"${statistics['filament_cost']:.2f}")
    
    if statistics.get('filament_cost_per_extruder'):
        per_ext_cost = _format_filament_list(
            [f"${v:.2f}" for v in statistics['filament_cost_per_extruder']]
        )
        if per_ext_cost:
            stats_table.add_row("Filament Cost Per Extruder", per_ext_cost)
    
    if statistics.get('filament_changes') and statistics['filament_changes'] > 0:
        stats_table.add_row("Filament Changes", str(statistics['filament_changes']))
    
    # Filament info
    if statistics.get('filament_names'):
        names = statistics['filament_names']
        for i, name in enumerate(names):
            if name:
                label = f"Filament {i+1}" if len(names) > 1 else "Filament"
                stats_table.add_row(label, f"[magenta]{name}[/magenta]")
    
    if statistics.get('filament_vendor'):
        vendors = [v for v in statistics['filament_vendor'] if v]
        if vendors:
            stats_table.add_row("Filament Vendor", ', '.join(vendors))
    
    if statistics.get('filament_types'):
        types = [t for t in statistics['filament_types'] if t]
        if types:
            stats_table.add_row("Filament Type", ', '.join(types))
    
    if statistics.get('filament_colors'):
        colors = statistics['filament_colors']
        if isinstance(colors, list):
            # Convert hex colors to styled names with color blocks
            styled_colors = []
            for c in colors:
                name, style = _hex_to_color_name(c)
                # Use Unicode block character with color styling
                styled_colors.append(f"[{style}]██[/{style}] {name}")
            color_display = ', '.join(styled_colors)
        else:
            name, style = _hex_to_color_name(str(colors))
            color_display = f"[{style}]██[/{style}] {name}"
        if color_display:
            stats_table.add_row("Filament Colors", color_display)
    
    # Filament properties
    if statistics.get('filament_density'):
        density = statistics['filament_density']
        if isinstance(density, list) and density:
            stats_table.add_row("Filament Density", f"{density[0]} g/cm3")
    
    if statistics.get('filament_diameter'):
        diameter = statistics['filament_diameter']
        if isinstance(diameter, list) and diameter:
            stats_table.add_row("Filament Diameter", f"{diameter[0]} mm")
    
    if statistics.get('enable_prime_tower'):
        prime_val = statistics['enable_prime_tower']
        if prime_val == '1':
            stats_table.add_row("Prime Tower", "[green]On[/green]")
        elif prime_val == '0':
            stats_table.add_row("Prime Tower", "[dim]Off[/dim]")
        else:
            stats_table.add_row("Prime Tower", prime_val)
    
    # Temperatures
    stats_table.add_row("", "")  # Separator
    
    if statistics.get('first_layer_nozzle_temp'):
        stats_table.add_row("First Layer Nozzle Temp", f"[red]{statistics['first_layer_nozzle_temp']}°C[/red]")
    
    if statistics.get('nozzle_temp'):
        temps = statistics['nozzle_temp']
        if isinstance(temps, list) and temps:
            stats_table.add_row("Nozzle Temp", f"[red]{temps[0]}°C[/red]")
    
    if statistics.get('first_layer_bed_temp'):
        stats_table.add_row("First Layer Bed Temp", f"[red]{statistics['first_layer_bed_temp']}°C[/red]")
    
    if statistics.get('bed_temp'):
        stats_table.add_row("Bed Temp", f"[red]{statistics['bed_temp']}°C[/red]")
    
    console.print(Panel(stats_table,
                        title="[bold bright_yellow]STATISTICS[/bold bright_yellow]",
                        border_style="grey50", box=box.ROUNDED))


def _print_objects_table_gcode(console: Console, objects: List[str]):
    """Print objects table for gcode files (names only, no per-object settings)."""
    if not objects:
        console.print("\n[red]No objects found[/red]")
        return
    
    console.rule("[bold bright_yellow]OBJECTS[/bold bright_yellow]", style="grey50")
    
    table = Table(box=box.ROUNDED, show_lines=False, header_style="bold blue", expand=True, border_style="grey50")
    table.add_column("#", justify="center", style="dim", width=5)
    table.add_column("Name", style="white", min_width=30)
    
    for i, obj_name in enumerate(objects, 1):
        table.add_row(str(i), f"[bold white]{escape(obj_name)}[/bold white]")
    
    console.print(table)


def _format_object_value(val, is_custom: bool, default, show_diff: bool) -> str:
    """Format object setting value with optional custom/diff markers.
    
    Args:
        val: The value to format.
        is_custom: Whether the value differs from profile default.
        default: The profile default value (shown in diff mode).
        show_diff: Whether to show the default value comparison.
        
    Returns:
        Formatted string with Rich markup for styling.
    """
    if not val:
        return ""
    s = str(val)
    if is_custom and default and show_diff:
        return f"[bold yellow]*{s}[/bold yellow] [dim]←{default}[/dim]"
    elif is_custom:
        return f"[bold yellow]*{s}[/bold yellow]"
    return s


def _format_support_value(support: str, is_custom: bool) -> str:
    """Format support enable/disable value with color coding.
    
    Args:
        support: Support status ('On', 'Off', or empty).
        is_custom: Whether the value differs from profile default.
        
    Returns:
        Formatted string with Rich markup (green for On, dim for Off).
    """
    if support == '':
        return ""
    elif support == 'On':
        if is_custom:
            return "[bold yellow]*On[/bold yellow]"
        return "[green]On[/green]"
    else:
        if is_custom:
            return "[bold yellow]*Off[/bold yellow]"
        return "[dim]Off[/dim]"


def _print_objects_table(console: Console, rows: List[Dict], profile: Dict[str, Any],
                         profile_full: Dict[str, Any], show_diff: bool, wiki_key):
    if not rows:
        console.print("\n[red]No objects found[/red]")
        return
    
    console.rule("[bold bright_yellow]OBJECTS[/bold bright_yellow]", style="grey50")
    
    table = Table(box=box.ROUNDED, show_lines=False, header_style="bold blue", expand=True, border_style="grey50")
    table.add_column("Plate", justify="center", style="white", width=5)
    table.add_column("Name", style="white", min_width=20, max_width=50)
    table.add_column("Filament", justify="center", width=8)
    table.add_column("Layer Height", justify="center")
    table.add_column("Wall Loops", justify="center")
    table.add_column("Infill Density", justify="center")
    table.add_column("Support", justify="center", width=7)
    table.add_column("Brim Type", justify="center")
    table.add_column("Outer Wall Speed", justify="center")
    
    current_plate = None
    for row in rows:
        plate_num = str(row['plate']) if row['plate'] else ""
        name = row['name']
        fil = row['filament']
        
        # Separators
        if row['is_parent'] and current_plate is not None:
            if plate_num and plate_num != current_plate:
                table.add_section()
                table.add_section()
            else:
                table.add_section()
        if plate_num:
            current_plate = plate_num
        
        # Plate number with distinct color
        if plate_num:
            plate_idx = int(plate_num) - 1 if plate_num.isdigit() else 0
            plate_color = PLATE_COLORS[plate_idx % len(PLATE_COLORS)]
            plate_styled = f"[bold {plate_color}]{plate_num}[/bold {plate_color}]"
        else:
            plate_styled = ""
        
        # Filament color by number
        fil_num = int(fil) if fil.isdigit() else 0
        fil_color = FILAMENT_COLORS[(fil_num - 1) % len(FILAMENT_COLORS)] if fil_num > 0 else 'white'
        fil_styled = f"[{fil_color}]{fil}[/{fil_color}]" if fil else ""
        
        layer = _format_object_value(row['layer_height'], row['layer_custom'], profile['layer_height'], show_diff)
        walls = _format_object_value(row['wall_loops'], row['walls_custom'], profile['wall_loops'], show_diff)
        infill = _format_object_value(row['infill'], row['infill_custom'], profile['sparse_infill_density'], show_diff)
        support = _format_support_value(row['support'], row['support_custom'])
        brim = _format_object_value(row['brim'], row['brim_custom'], profile['brim_type'], show_diff)
        speed = _format_object_value(row['outer_wall_speed'], row['speed_custom'], profile['outer_wall_speed'], show_diff)
        
        # Name style (escape to prevent Rich markup injection from object names)
        safe_name = escape(name)
        if row['is_parent']:
            name_style = f"[bold white]{safe_name}[/bold white]"
        else:
            name_style = f"[dim]{safe_name}[/dim]"
        
        table.add_row(plate_styled, name_style, fil_styled, layer, walls, infill, support, brim, speed)
        
        # Custom settings for object/part
        custom_settings = row.get('custom_settings', {})
        if custom_settings:
            settings_items = list(custom_settings.items())
            for idx, (key, value) in enumerate(settings_items):
                is_last = (idx == len(settings_items) - 1)
                branch = "└─" if is_last else "├─"
                default_val = profile_full.get(key, '')
                linked_key = wiki_key(key)
                if show_diff and default_val and str(default_val) != str(value):
                    setting_name = f"    [dim]{branch}[/dim] [yellow]{linked_key}: {value}[/yellow] [dim]←{default_val}[/dim]"
                else:
                    setting_name = f"    [dim]{branch}[/dim] [yellow]{linked_key}: {value}[/yellow]"
                table.add_row("", setting_name, "", "", "", "", "", "", "")
    
    console.print(table)
    console.print("[bold yellow]*[/bold yellow] = custom value (overrides profile default)")
    print()


def print_results(result: Dict[str, Any], show_diff: bool = False, no_color: bool = False, wiki: bool = False):
    """Format and display analysis results using Rich tables (for 3MF files)."""
    wiki_label, wiki_key = _make_wiki_helpers(wiki)
    console = Console(no_color=no_color)
    profile = result['profile']
    profile_full = result.get('profile_full', {})
    
    _print_header(console, result['file'])
    _print_profile_panel(console, profile)
    _print_global_settings(console, profile, wiki_label)
    _print_custom_global(console, result['custom_global'], wiki_key)
    _print_objects_table(console, result['rows'], profile, profile_full, show_diff, wiki_key)


def print_gcode_results(result: Dict[str, Any], show_diff: bool = False, no_color: bool = False, wiki: bool = False):
    """Format and display analysis results for gcode files."""
    wiki_label, wiki_key = _make_wiki_helpers(wiki)
    console = Console(no_color=no_color)
    profile = result['profile']
    profile_full = result.get('profile_full', {})
    
    # Use different header for gcode
    console.print(Panel(f"[bold cyan]GCODE SETTINGS ANALYZER[/bold cyan]  |  {result['file']}", 
                        border_style="cyan"))
    
    # Profile panel (same as 3MF) - at the top
    _print_profile_panel(console, profile)
    
    # Global settings (same as 3MF)
    _print_global_settings(console, profile, wiki_label)
    
    # Custom global settings (same as 3MF)
    _print_custom_global(console, result['custom_global'], wiki_key)
    
    # Objects list (gcode has no per-object settings, only names)
    _print_objects_table_gcode(console, result.get('objects', []))
    
    # Statistics panel (gcode-specific) - at the bottom
    _print_statistics_panel(console, result.get('statistics', {}))


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the application."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(levelname)s: %(message)s'
    )


def _get_file_type(filepath: Path) -> str:
    """Determine file type based on extension.
    
    Returns:
        '3mf', 'gcode', or 'unknown'
    """
    suffix = filepath.suffix.lower()
    if suffix == FILE_EXTENSION_3MF:
        return '3mf'
    elif suffix == FILE_EXTENSION_GCODE:
        return 'gcode'
    return 'unknown'


def main():
    parser = argparse.ArgumentParser(
        description='3MF/Gcode Settings Analyzer - Analyze 3MF and Gcode files and display slicer settings',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python analyze.py model.3mf
  python analyze.py model.gcode
  python analyze.py model.3mf --diff
  python analyze.py model.3mf --json
  python analyze.py model.3mf --verbose
  python analyze.py model.3mf --wiki
  python analyze.py model.3mf --no-color > output.txt
  python analyze.py --update-wiki
"""
    )
    parser.add_argument('file', nargs='?', help='Path to 3MF or Gcode file')
    parser.add_argument('--diff', action='store_true', 
                        help='Show comparison with global settings')
    parser.add_argument('--json', action='store_true',
                        help='Output JSON only (no formatted tables)')
    parser.add_argument('--no-color', action='store_true',
                        help='Disable colored output (for Rich library)')
    parser.add_argument('--wiki', '-w', action='store_true',
                        help='Add clickable wiki links to setting names (Cmd/Ctrl+click)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose logging')
    parser.add_argument('--version', action='version',
                        version=f'%(prog)s {__version__}')
    parser.add_argument('--update-wiki', action='store_true',
                        help='Update settings wiki data from OrcaSlicer GitHub')
    parser.add_argument('--force-update-wiki', action='store_true',
                        help='Force re-download wiki data even if up to date')
    
    args = parser.parse_args()
    
    setup_logging(verbose=args.verbose)
    
    # Handle wiki update commands (no file required)
    if args.update_wiki or args.force_update_wiki:
        from settings_wiki import update as wiki_update
        console = Console(no_color=args.no_color)
        console.print("[cyan]Updating wiki data from OrcaSlicer GitHub...[/cyan]")
        try:
            updated = wiki_update(force=args.force_update_wiki)
            if updated:
                console.print("[green]Wiki data updated successfully.[/green]")
            else:
                console.print("[yellow]Wiki data is already up to date.[/yellow]")
        except Exception as e:
            logger.error("Failed to update wiki data: %s", e)
            console.print(f"[red]Failed to update wiki data: {e}[/red]")
            if not args.file:
                sys.exit(1)
        if not args.file:
            sys.exit(0)
    
    filepath = Path(args.file) if args.file else None
    
    if filepath is None:
        parser.error("the following arguments are required: file")
    
    if not filepath.exists():
        logger.error("File not found: %s", filepath)
        sys.exit(1)
    
    file_type = _get_file_type(filepath)
    
    if file_type == 'unknown':
        logger.error("Unsupported file type: %s (use .3mf or .gcode)", filepath.suffix)
        sys.exit(1)
    
    try:
        if file_type == '3mf':
            analyzer = ThreeMFAnalyzer(str(filepath))
            result = analyzer.analyze()
            
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print_results(result, show_diff=args.diff, no_color=args.no_color, wiki=args.wiki)
        
        elif file_type == 'gcode':
            analyzer = GcodeAnalyzer(filepath)
            result = analyzer.analyze()
            
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print_gcode_results(result, show_diff=args.diff, no_color=args.no_color, wiki=args.wiki)
            
    except zipfile.BadZipFile:
        logger.error("Invalid or corrupted ZIP/3MF file: %s", filepath)
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse project settings (invalid JSON): %s", e)
        sys.exit(1)
    except ET.ParseError as e:
        logger.error("Failed to parse model settings (invalid XML): %s", e)
        sys.exit(1)
    except ValueError as e:
        # Security-related errors (e.g., Zip Slip attack detection)
        logger.error("Security or validation error: %s", e)
        sys.exit(1)
    except OSError as e:
        # File system errors (permissions, disk full, etc.)
        logger.error("File system error: %s", e)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(130)


if __name__ == "__main__":
    main()
