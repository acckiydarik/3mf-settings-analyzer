#!/usr/bin/env python3
"""
3MF Settings Analyzer
Analyzes 3MF files and displays slicer settings in a structured table format.
Supports Bambu Studio, OrcaSlicer, Snapmaker Orca, and other slicers using the same 3MF metadata format.
"""

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

# Filament colors by number for table display
FILAMENT_COLORS = ('cyan', 'magenta', 'green', 'yellow', 'blue', 'red')

# Plate colors - neutral/orange tones, different from filament colors
PLATE_COLORS = ('white', 'dark_orange', 'wheat1', 'grey50')


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
        """Extract 3MF archive"""
        self.temp_dir = Path(tempfile.mkdtemp())
        with zipfile.ZipFile(self.filepath, 'r') as z:
            z.extractall(self.temp_dir)
    
    def _cleanup(self):
        """Cleanup temporary files"""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def _parse_project_settings(self):
        """Parse project_settings.config (JSON)"""
        config_path = self.temp_dir / "Metadata" / "project_settings.config"
        if config_path.exists():
            logger.debug("Parsing project settings from: %s", config_path)
            with open(config_path, 'r', encoding='utf-8') as f:
                self.project_settings = json.load(f)
        else:
            logger.warning("Project settings file not found: %s", config_path)
    
    def _parse_model_settings(self):
        """Parse model_settings.config (XML)"""
        config_path = self.temp_dir / "Metadata" / "model_settings.config"
        if not config_path.exists():
            logger.warning("Model settings file not found: %s", config_path)
            return
        
        logger.debug("Parsing model settings from: %s", config_path)
        
        tree = ET.parse(config_path)
        root = tree.getroot()
        
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
                elif key in ('sparse_infill_density', 'skeleton_infill_density'):
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
            
            # Sort by identify_id descending (like slicer does)
            plate_objects.sort(key=lambda x: x['identify_id'], reverse=True)
            
            if plate_id:
                self.plates.append({
                    'id': plate_id,
                    'name': plate_name,
                    'objects': [obj['object_id'] for obj in plate_objects]
                })
    
    def _get_value(self, key: str, default=None):
        """Get value from project_settings"""
        val = self.project_settings.get(key, default)
        if isinstance(val, list) and len(val) >= 1:
            return val[0]
        return val
    
    def _get_custom_global_settings(self) -> Dict[str, Any]:
        """Extract custom global settings"""
        custom = {}
        
        diff_settings = self.project_settings.get('different_settings_to_system', [])
        if diff_settings and diff_settings[0]:
            keys = diff_settings[0].split(';')
            for key in keys:
                key = key.strip()
                if key and key in self.project_settings:
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
                    'support': 'On' if obj_support == '1' else 'Off',
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
                    
                    # Inherit support from parent
                    part_support = 'On' if obj_support == '1' else 'Off'
                    
                    rows.append({
                        'plate': '',
                        'name': f"  {part_name}",
                        'is_parent': False,
                        'is_part': True,
                        'filament': part_extruder,
                        'layer_height': '',
                        'layer_custom': False,
                        'wall_loops': obj_walls,
                        'walls_custom': False,
                        'infill': self._format_infill(obj_infill),
                        'infill_custom': False,
                        'support': part_support,
                        'support_custom': False,
                        'brim': '',
                        'brim_custom': False,
                        'outer_wall_speed': obj_speed,
                        'speed_custom': False,
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

def print_results(result: Dict[str, Any], show_diff: bool = False, no_color: bool = False):
    """Format and display analysis results using Rich tables."""
    
    console = Console(no_color=no_color)
    profile = result['profile']
    profile_full = result.get('profile_full', {})
    
    # ═══════════════════════════════════════════════════════════
    # HEADER
    # ═══════════════════════════════════════════════════════════
    console.print()
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
    
    console.print("\n[bold yellow]PROFILE[/bold yellow]")
    console.print(profile_table)
    
    # ═══════════════════════════════════════════════════════════
    # PROFILE SETTINGS
    # ═══════════════════════════════════════════════════════════
    settings_table = Table(show_header=False, box=None, padding=(0, 2))
    settings_table.add_column("Key", style="dim")
    settings_table.add_column("Value", style="white")
    
    # Basic
    settings_table.add_row("Layer Height", f"{profile['layer_height']} mm")
    if profile['initial_layer_print_height']:
        settings_table.add_row("Initial Layer Print Height", f"{profile['initial_layer_print_height']} mm")
    if profile['line_width']:
        settings_table.add_row("Line Width", f"{profile['line_width']} mm")
    if profile['print_flow_ratio'] and profile['print_flow_ratio'] != '1':
        settings_table.add_row("Print Flow Ratio", f"{float(profile['print_flow_ratio'])*100:.0f}%")
    elif profile['filament_flow_ratio']:
        settings_table.add_row("Filament Flow Ratio", profile['filament_flow_ratio'])
    settings_table.add_row("Wall Loops", profile['wall_loops'])
    settings_table.add_row("Sparse Infill Density", profile['sparse_infill_density'])
    settings_table.add_row("Top/Bottom Shell Layers", f"{profile['top_shell_layers']}/{profile['bottom_shell_layers']}")
    settings_table.add_row("Brim Type", profile['brim_type'])
    settings_table.add_row("Enable Support", "On" if profile['enable_support'] == '1' else "Off")
    settings_table.add_row("Seam Position", profile['seam_position'])
    
    console.print("\n[bold yellow]GLOBAL SETTINGS[/bold yellow]")
    console.print(settings_table)
    
    # Speeds
    speed_table = Table(show_header=False, box=None, padding=(0, 2))
    speed_table.add_column("Key", style="dim")
    speed_table.add_column("Value", style="cyan")
    
    if profile['initial_layer_speed']:
        speed_table.add_row("Initial Layer Speed", f"{profile['initial_layer_speed']} mm/s")
    speed_table.add_row("Outer Wall Speed", f"{profile['outer_wall_speed']} mm/s")
    speed_table.add_row("Inner Wall Speed", f"{profile['inner_wall_speed']} mm/s")
    if profile['sparse_infill_speed']:
        speed_table.add_row("Sparse Infill Speed", f"{profile['sparse_infill_speed']} mm/s")
    if profile['top_surface_speed']:
        speed_table.add_row("Top Surface Speed", f"{profile['top_surface_speed']} mm/s")
    speed_table.add_row("Travel Speed", f"{profile['travel_speed']} mm/s")
    speed_table.add_row("Bridge Speed", f"{profile['bridge_speed']} mm/s")
    
    console.print()
    console.print(speed_table)
    
    # Patterns and modes
    pattern_table = Table(show_header=False, box=None, padding=(0, 2))
    pattern_table.add_column("Key", style="dim")
    pattern_table.add_column("Value", style="white")
    
    pattern_table.add_row("Sparse Infill Pattern", profile['sparse_infill_pattern'])
    pattern_table.add_row("Top Surface Pattern", profile['top_surface_pattern'])
    pattern_table.add_row("Print Sequence", profile['print_sequence'])
    
    # Special modes (only if enabled)
    if profile['spiral_mode'] == '1':
        pattern_table.add_row("Spiral Mode (Vase)", "[bright_green]ON[/bright_green]")
    if profile['ironing_type'] != 'no ironing':
        pattern_table.add_row("Ironing Type", f"[bright_green]{profile['ironing_type']}[/bright_green]")
    if profile['fuzzy_skin'] != 'none':
        pattern_table.add_row("Fuzzy Skin", f"[bright_green]{profile['fuzzy_skin']}[/bright_green]")
    
    console.print()
    console.print(pattern_table)
    
    # Retract / Z-hop / PA
    retract_table = Table(show_header=False, box=None, padding=(0, 2))
    retract_table.add_column("Key", style="dim")
    retract_table.add_column("Value", style="white")
    
    retract_table.add_row("Retraction Length", f"{profile['retraction_length']} mm")
    if profile['retraction_speed']:
        retract_table.add_row("Retraction Speed", f"{profile['retraction_speed']} mm/s")
    retract_table.add_row("Z-Hop", f"{profile['z_hop']} mm")
    if profile['pressure_advance']:
        retract_table.add_row("Pressure Advance", profile['pressure_advance'])
    
    # Fan
    if profile['fan_min_speed'] or profile['fan_max_speed']:
        retract_table.add_row("Fan Min/Max Speed", f"{profile['fan_min_speed']}% / {profile['fan_max_speed']}%")
    
    # Cooling
    if profile['slow_down_for_layer_cooling'] == '1':
        retract_table.add_row("Slow Down for Layer Cooling", f"[green]On[/green] ({profile['slow_down_layer_time']}s)")
    else:
        retract_table.add_row("Slow Down for Layer Cooling", "[dim]Off[/dim]")
    
    console.print()
    console.print(retract_table)
    
    # Temperatures
    temp_table = Table(show_header=False, box=None, padding=(0, 2))
    temp_table.add_column("Key", style="dim")
    temp_table.add_column("Value", style="bright_red")
    
    temp_table.add_row("Nozzle Temperature", f"{profile['nozzle_temperature']}°C")
    if profile['bed_temperature']:
        temp_table.add_row("Bed Temperature", f"{profile['bed_temperature']}°C")
    
    console.print()
    console.print(temp_table)
    
    # Advanced flags
    flags = []
    if profile['enable_arc_fitting'] == '1':
        flags.append('Enable Arc Fitting')
    if profile['enable_overhang_speed'] == '1':
        flags.append('Enable Overhang Speed')
    if profile['timelapse_type'] != '0':
        flags.append(f"Timelapse Type: {profile['timelapse_type']}")
    if flags:
        console.print(f"  [dim]Features:[/dim]  [bright_cyan]{', '.join(flags)}[/bright_cyan]")
    
    # ═══════════════════════════════════════════════════════════
    # CUSTOM GLOBAL
    # ═══════════════════════════════════════════════════════════
    custom = result['custom_global']
    if custom:
        console.print("\n[bold red]CUSTOM GLOBAL SETTINGS[/bold red] [dim](changed from profile)[/dim]")
        for k, v in custom.items():
            console.print(f"  [yellow]✎ {k}[/yellow]: {escape(str(v))}", highlight=False)
    
    # ═══════════════════════════════════════════════════════════
    # OBJECTS TABLE
    # ═══════════════════════════════════════════════════════════
    rows = result['rows']
    if not rows:
        console.print("\n[red]No objects found[/red]")
        return
    
    console.print("\n[bold yellow]OBJECTS[/bold yellow]")
    
    table = Table(box=box.ROUNDED, show_lines=False, header_style="bold blue")
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
                if show_diff and default_val and str(default_val) != str(value):
                    setting_name = f"    [dim]{branch}[/dim] [yellow]{key}: {value}[/yellow] [dim]←{default_val}[/dim]"
                else:
                    setting_name = f"    [dim]{branch}[/dim] [yellow]{key}: {value}[/yellow]"
                # Empty row with setting only in Name column
                table.add_row("", setting_name, "", "", "", "", "", "", "")
    
    console.print(table)
    
    # Legend
    console.print()
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
  python analyze.py model.3mf --no-color > output.txt
"""
    )
    parser.add_argument('file', help='Path to 3MF file')
    parser.add_argument('--diff', action='store_true', 
                        help='Show comparison with global settings')
    parser.add_argument('--json', action='store_true',
                        help='Output raw JSON data')
    parser.add_argument('--no-color', action='store_true',
                        help='Disable colored output (for Rich library)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose logging')
    
    args = parser.parse_args()
    
    setup_logging(verbose=args.verbose)
    
    filepath = Path(args.file)
    
    if not filepath.exists():
        logger.error("File not found: %s", filepath)
        sys.exit(1)
    
    if filepath.suffix.lower() != '.3mf':
        logger.warning("File does not have .3mf extension: %s", filepath)
    
    try:
        analyzer = ThreeMFAnalyzer(str(filepath))
        result = analyzer.analyze()
        print_results(result, show_diff=args.diff, no_color=args.no_color)
        
        if args.json:
            print("\n--- JSON OUTPUT ---")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
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
