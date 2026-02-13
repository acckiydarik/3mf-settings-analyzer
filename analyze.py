#!/usr/bin/env python3
"""
3MF Settings Analyzer
Analyzes 3MF files and displays slicer settings in a structured table format.
Supports Bambu Studio, OrcaSlicer, Snapmaker Orca, and other slicers using the same 3MF metadata format.
"""

__version__ = "1.2.0"

import zipfile
import json
import xml.etree.ElementTree as ET
import tempfile
import shutil
import sys
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

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


# ═══════════════════════════════════════════════════════════════
# Analyzer
# ═══════════════════════════════════════════════════════════════

class ThreeMFAnalyzer:
    """Analyzes 3MF files and extracts slicer settings."""
    
    def __init__(self, filepath: str):
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
                    if not str(target_path).startswith(str(self.temp_dir.resolve())):
                        raise ValueError(f"Path traversal detected in archive: {member}")
                z.extractall(self.temp_dir)
        except Exception:
            # Cleanup temp directory if extraction fails
            if self.temp_dir and self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
            self.temp_dir = None
            raise
    
    def _cleanup(self):
        """Cleanup temporary files"""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def _parse_project_settings(self):
        """Parse project_settings.config (JSON)"""
        config_path = self.temp_dir / "Metadata" / "project_settings.config"
        if config_path.exists():
            logger.debug("Parsing project settings from: %s", config_path)
            try:
                with open(config_path, 'r', encoding='utf-8', errors='replace') as f:
                    self.project_settings = json.load(f)
            except UnicodeDecodeError as e:
                logger.error("Encoding error reading project settings: %s", e)
                raise
        else:
            logger.warning("Project settings file not found: %s", config_path)
    
    def _parse_model_settings(self):
        """Parse model_settings.config (XML)"""
        config_path = self.temp_dir / "Metadata" / "model_settings.config"
        if not config_path.exists():
            logger.warning("Model settings file not found: %s", config_path)
            return
        
        logger.debug("Parsing model settings from: %s", config_path)
        
        try:
            tree = ET.parse(config_path)
            root = tree.getroot()
        except ET.ParseError as e:
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
                'extruder': '1',
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
                            identify_id = 0
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
            return val[index] if len(val) > index else default
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
            'layer_height': self._get_value('layer_height', '0.2'),
            'initial_layer_print_height': self._get_value('initial_layer_print_height', ''),
            'nozzle': self._get_value('nozzle_diameter', '0.4'),
            'line_width': self._get_value('line_width', ''),
            'wall_loops': self._get_value('wall_loops', '2'),
            'sparse_infill_density': self._get_value('sparse_infill_density', '15%'),
            'brim_type': self._get_value('brim_type', 'no_brim'),
            'enable_support': self._get_value('enable_support', '0'),
            # Flow
            'print_flow_ratio': self._get_value('print_flow_ratio', '1'),
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
            'ironing_type': self._get_value('ironing_type', 'no ironing'),
            'fuzzy_skin': self._get_value('fuzzy_skin', 'none'),
            'spiral_mode': self._get_value('spiral_mode', '0'),
            # Retraction and Z
            'retraction_length': self._get_value('retraction_length', ''),
            'retraction_speed': self._get_value('retraction_speed', ''),
            'z_hop': self._get_value('z_hop', ''),
            # Fan
            'fan_min_speed': self._get_value('fan_min_speed', ''),
            'fan_max_speed': self._get_value('fan_max_speed', ''),
            # Cooling
            'slow_down_for_layer_cooling': self._get_value('slow_down_for_layer_cooling', '0'),
            'slow_down_layer_time': self._get_value('slow_down_layer_time', ''),
            # Advanced
            'pressure_advance': self._get_value('pressure_advance', ''),
            'enable_arc_fitting': self._get_value('enable_arc_fitting', '0'),
            'enable_overhang_speed': self._get_value('enable_overhang_speed', '0'),
            # Print modes
            'print_sequence': self._get_value('print_sequence', 'by layer'),
            'timelapse_type': self._get_value('timelapse_type', '0'),
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
    
    def _format_infill(self, value):
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
                obj_extruder = obj.get('extruder', '1')
                
                def is_custom(obj_val, global_val):
                    if obj_val is None:
                        return False
                    return str(obj_val) != str(global_val)
                
                rows.append({
                    'plate': plate_num,
                    'name': obj_name,
                    'is_parent': True,
                    'is_part': False,
                    'filament': obj_extruder,
                    'layer_height': obj_layer,
                    'layer_custom': is_custom(obj.get('layer_height'), profile['layer_height']),
                    'wall_loops': obj_walls,
                    'walls_custom': is_custom(obj.get('wall_loops'), profile['wall_loops']),
                    'infill': self._format_infill(obj_infill),
                    'infill_custom': is_custom(obj.get('sparse_infill_density'), profile['sparse_infill_density']),
                    'support': 'On' if obj_support == BOOL_TRUE else 'Off',
                    'support_custom': is_custom(obj.get('enable_support'), profile['enable_support']),
                    'brim': self._format_brim(obj_brim),
                    'brim_custom': is_custom(obj.get('brim_type'), profile['brim_type']),
                    'outer_wall_speed': obj_speed,
                    'speed_custom': is_custom(obj.get('outer_wall_speed'), profile['outer_wall_speed']),
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


# ═══════════════════════════════════════════════════════════════
# Output
# ═══════════════════════════════════════════════════════════════

def _make_wiki_helpers(enabled: bool):
    """Create wiki_label and wiki_key helpers based on --wiki flag.

    When disabled, returns no-op passthrough functions to avoid
    importing settings_wiki module entirely.
    """
    if not enabled:
        return (
            lambda display_name, setting_key: display_name,
            lambda setting_key: setting_key,
        )

    from settings_wiki import get_wiki_url
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


def print_results(result: Dict[str, Any], show_diff: bool = False, no_color: bool = False, wiki: bool = False):
    """Format and display analysis results using Rich tables."""
    
    wiki_label, wiki_key = _make_wiki_helpers(wiki)
    console = Console(no_color=no_color)
    profile = result['profile']
    profile_full = result.get('profile_full', {})
    
    # ═══════════════════════════════════════════════════════════
    # HEADER
    # ═══════════════════════════════════════════════════════════
    console.print(Panel(f"[bold cyan]3MF SETTINGS ANALYZER[/bold cyan]  │  {result['file']}", 
                        border_style="cyan"))
    
    # ═══════════════════════════════════════════════════════════
    # PROFILE
    # ═══════════════════════════════════════════════════════════
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
    
    # ═══════════════════════════════════════════════════════════
    # GLOBAL SETTINGS (single merged table with section dividers)
    # ═══════════════════════════════════════════════════════════
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
        gs.add_row(wiki_label("Print Flow Ratio", "print_flow_ratio"), f"{float(profile['print_flow_ratio'])*100:.0f}%")
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
    if profile['ironing_type'] != 'no ironing':
        gs.add_row(wiki_label("Ironing Type", "ironing_type"), f"[bright_green]{profile['ironing_type']}[/bright_green]")
    if profile['fuzzy_skin'] != 'none':
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
    else:
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
    if profile['timelapse_type'] != '0':
        flags.append(f"Timelapse Type: {profile['timelapse_type']}")
    if flags:
        gs.add_row("", "")
        gs.add_row("[dim]Features[/dim]", f"[bright_cyan]{', '.join(flags)}[/bright_cyan]")
    
    console.print(Panel(gs, title="[bold bright_yellow]GLOBAL SETTINGS[/bold bright_yellow]",
                        border_style="grey50", box=box.ROUNDED))
    
    # ═══════════════════════════════════════════════════════════
    # CUSTOM GLOBAL
    # ═══════════════════════════════════════════════════════════
    custom = result['custom_global']
    if custom:
        custom_table = Table(show_header=False, box=None, padding=(0, 2))
        custom_table.add_column("Key", style="yellow")
        custom_table.add_column("Value", style="white")
        for k, v in custom.items():
            custom_table.add_row(f"✎ {wiki_key(k)}", escape(str(v)))
        console.print(Panel(custom_table,
                            title="[bold bright_red]CUSTOM GLOBAL SETTINGS[/bold bright_red] [grey50](changed from profile)[/grey50]",
                            border_style="grey50", box=box.ROUNDED))
    
    # ═══════════════════════════════════════════════════════════
    # OBJECTS TABLE
    # ═══════════════════════════════════════════════════════════
    rows = result['rows']
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
        # Format values
        plate_num = str(row['plate']) if row['plate'] else ""
        name = row['name']
        fil = row['filament']
        
        # Separators
        if row['is_parent'] and current_plate is not None:
            if plate_num and plate_num != current_plate:
                # Different plate - double section (more visible)
                table.add_section()
                table.add_section()
            else:
                # Same plate, different object - single section
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
        
        def fmt_val(val, is_custom, default=None):
            if not val:
                return ""
            s = str(val)
            if is_custom and default and show_diff:
                return f"[bold yellow]*{s}[/bold yellow] [dim]←{default}[/dim]"
            elif is_custom:
                return f"[bold yellow]*{s}[/bold yellow]"
            return s
        
        layer = fmt_val(row['layer_height'], row['layer_custom'], profile['layer_height'])
        walls = fmt_val(row['wall_loops'], row['walls_custom'], profile['wall_loops'])
        infill = fmt_val(row['infill'], row['infill_custom'], profile['sparse_infill_density'])
        # Support with custom highlighting (empty for parts)
        if row['support'] == '':
            support = ""
        elif row['support'] == 'On':
            if row['support_custom']:
                support = "[bold yellow]*On[/bold yellow]"
            else:
                support = "[green]On[/green]"
        else:
            if row['support_custom']:
                support = "[bold yellow]*Off[/bold yellow]"
            else:
                support = "[dim]Off[/dim]"
        brim = fmt_val(row['brim'], row['brim_custom'], profile['brim_type'])
        speed = fmt_val(row['outer_wall_speed'], row['speed_custom'], profile['outer_wall_speed'])
        
        # Name style
        if row['is_parent']:
            name_style = "[bold white]" + name + "[/bold white]"
        else:
            name_style = "[dim]" + name + "[/dim]"
        
        table.add_row(plate_styled, name_style, fil_styled, layer, walls, infill, support, brim, speed)
        
        # Custom settings for object/part
        custom_settings = row.get('custom_settings', {})
        if custom_settings:
            settings_items = list(custom_settings.items())
            for idx, (key, value) in enumerate(settings_items):
                is_last = (idx == len(settings_items) - 1)
                branch = "└─" if is_last else "├─"
                # Look for default value in full profile
                default_val = profile_full.get(key, '')
                linked_key = wiki_key(key)
                if show_diff and default_val and str(default_val) != str(value):
                    setting_name = f"    [dim]{branch}[/dim] [yellow]{linked_key}: {value}[/yellow] [dim]←{default_val}[/dim]"
                else:
                    setting_name = f"    [dim]{branch}[/dim] [yellow]{linked_key}: {value}[/yellow]"
                # Empty row with setting only in Name column
                table.add_row("", setting_name, "", "", "", "", "", "", "")
    
    console.print(table)
    
    # Legend
    console.print("[bold yellow]*[/bold yellow] = custom value (overrides profile default)")
    print()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the application."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(levelname)s: %(message)s'
    )


def main():
    parser = argparse.ArgumentParser(
        description='3MF Settings Analyzer - Analyze 3MF files and display slicer settings',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python analyze.py model.3mf
  python analyze.py model.3mf --diff
  python analyze.py model.3mf --json
  python analyze.py model.3mf --verbose
  python analyze.py model.3mf --wiki
  python analyze.py model.3mf --no-color > output.txt
  python analyze.py --update-wiki
"""
    )
    parser.add_argument('file', nargs='?', help='Path to 3MF file')
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
        wiki_update(force=args.force_update_wiki)
        if not args.file:
            sys.exit(0)
    
    filepath = Path(args.file) if args.file else None
    
    if filepath is None:
        parser.error("the following arguments are required: file")
    
    if not filepath.exists():
        logger.error("File not found: %s", filepath)
        sys.exit(1)
    
    if filepath.suffix.lower() != '.3mf':
        logger.warning("File does not have .3mf extension: %s", filepath)
    
    try:
        analyzer = ThreeMFAnalyzer(str(filepath))
        result = analyzer.analyze()
        
        if args.json:
            # JSON-only output for scripting/automation
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print_results(result, show_diff=args.diff, no_color=args.no_color, wiki=args.wiki)
            
    except zipfile.BadZipFile:
        logger.error("Invalid or corrupted ZIP/3MF file: %s", filepath)
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse project settings (invalid JSON): %s", e)
        sys.exit(1)
    except ET.ParseError as e:
        logger.error("Failed to parse model settings (invalid XML): %s", e)
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error while processing file: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
