"""Shared field definitions for output.py and compare.py.

Single source of truth for field order, labels, formatting, and display
conditions.  Both single-file rendering (output.py) and comparison rendering
(compare.py) iterate over these lists, so adding a new field means editing
exactly one place.

Each field is a 4-tuple:

    (label, wiki_key, formatter, condition)

- label      -- str or callable(Dict)->Tuple[str,str].
                If callable, returns (display_label, wiki_key) dynamically.
- wiki_key   -- str, used as default wiki key (ignored when label is callable).
- formatter  -- callable(Dict)->str, formats a single profile/stats dict into
                a Rich-markup string.
- condition  -- callable(Dict)->bool or None.  When not None the field is only
                shown if the condition is true (single mode) or true for at
                least one profile (compare mode).

``None`` in a field list represents a visual separator row.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from core.constants import BOOL_TRUE

FieldDef = Tuple[
    Union[str, Callable[[Dict], Tuple[str, str]]],
    str,
    Callable[[Dict], str],
    Optional[Callable[[Dict], bool]],
]

# Sentinel markers for renderer-specific multi-row content.  Renderers check
# ``field is RENDER_FILAMENT_NAMES`` (identity) and inject the appropriate
# rows at that position.
RENDER_FILAMENT_NAMES: Tuple[str] = ("__filament_names__",)
RENDER_FILAMENT_COLORS: Tuple[str] = ("__filament_colors__",)


# ═══════════════════════════════════════════════════════════════
# Factory helpers -- produce formatters and conditions
# ═══════════════════════════════════════════════════════════════

def _fmt_plain(key: str) -> Callable[[Dict], str]:
    """Value as-is."""
    def _fmt(p: Dict) -> str:
        return str(p.get(key, ''))
    return _fmt


def _fmt_mm(key: str) -> Callable[[Dict], str]:
    """Value + ' mm'."""
    def _fmt(p: Dict) -> str:
        v = p.get(key, '')
        return f"{v} mm" if v else ""
    return _fmt


def _fmt_speed(key: str) -> Callable[[Dict], str]:
    """Cyan-styled value + ' mm/s'."""
    def _fmt(p: Dict) -> str:
        v = p.get(key, '')
        return f"[cyan]{v} mm/s[/cyan]" if v else ""
    return _fmt


def _fmt_temp(key: str) -> Callable[[Dict], str]:
    """Red-styled value + degree C."""
    def _fmt(p: Dict) -> str:
        v = p.get(key, '')
        return f"[red]{v}\u00b0C[/red]" if v else ""
    return _fmt


def _fmt_green(key: str) -> Callable[[Dict], str]:
    """Green-styled value."""
    def _fmt(p: Dict) -> str:
        v = p.get(key, '')
        return f"[green]{v}[/green]" if v else ""
    return _fmt


def _fmt_magenta(key: str) -> Callable[[Dict], str]:
    """Magenta-styled value."""
    def _fmt(p: Dict) -> str:
        v = p.get(key, '')
        return f"[magenta]{v}[/magenta]" if v else ""
    return _fmt


def _if_present(key: str) -> Callable[[Dict], bool]:
    """Condition: show only when value is truthy."""
    return lambda p: bool(p.get(key))


# ═══════════════════════════════════════════════════════════════
# Global Settings -- complex formatters
# ═══════════════════════════════════════════════════════════════

def _fmt_flow_ratio(p: Dict) -> str:
    if p.get('print_flow_ratio') and p['print_flow_ratio'] != '1':
        try:
            return f"{float(p['print_flow_ratio']) * 100:.0f}%"
        except (ValueError, TypeError):
            return str(p['print_flow_ratio'])
    elif p.get('filament_flow_ratio'):
        return p['filament_flow_ratio']
    return ""


def _flow_label(p: Dict) -> Tuple[str, str]:
    """Dynamic label for flow ratio -- changes depending on which key has data."""
    if p.get('print_flow_ratio') and p['print_flow_ratio'] != '1':
        return ("Print Flow Ratio", "print_flow_ratio")
    elif p.get('filament_flow_ratio'):
        return ("Filament Flow Ratio", "filament_flow_ratio")
    return ("", "")


def _has_flow(p: Dict) -> bool:
    return bool(_fmt_flow_ratio(p))


def _fmt_shell_layers(p: Dict) -> str:
    return f"{p.get('top_shell_layers', '')}/{p.get('bottom_shell_layers', '')}"


def _fmt_support_toggle(p: Dict) -> str:
    return "On" if p.get('enable_support') == BOOL_TRUE else "Off"


def _fmt_spiral(p: Dict) -> str:
    return "[bright_green]ON[/bright_green]" if p.get('spiral_mode') == BOOL_TRUE else ""


def _cond_spiral(p: Dict) -> bool:
    return p.get('spiral_mode') == BOOL_TRUE


def _fmt_ironing(p: Dict) -> str:
    v = p.get('ironing_type', '')
    if v and v not in ('no ironing', 'no_ironing'):
        return f"[bright_green]{v}[/bright_green]"
    return ""


def _cond_ironing(p: Dict) -> bool:
    v = p.get('ironing_type', '')
    return bool(v) and v not in ('no ironing', 'no_ironing')


def _fmt_fuzzy(p: Dict) -> str:
    v = p.get('fuzzy_skin', '')
    if v and v != 'none':
        return f"[bright_green]{v}[/bright_green]"
    return ""


def _cond_fuzzy(p: Dict) -> bool:
    v = p.get('fuzzy_skin', '')
    return bool(v) and v != 'none'


def _fmt_fan(p: Dict) -> str:
    mn = p.get('fan_min_speed', '')
    mx = p.get('fan_max_speed', '')
    if mn or mx:
        return f"{mn}% / {mx}%"
    return ""


def _cond_fan(p: Dict) -> bool:
    return bool(p.get('fan_min_speed') or p.get('fan_max_speed'))


def _fmt_cooling(p: Dict) -> str:
    v = p.get('slow_down_for_layer_cooling')
    if v == BOOL_TRUE:
        return f"[green]On[/green] ({p.get('slow_down_layer_time', '')}s)"
    elif v:
        return "[dim]Off[/dim]"
    return ""


def _cond_cooling(p: Dict) -> bool:
    return bool(p.get('slow_down_for_layer_cooling'))


def _fmt_features(p: Dict) -> str:
    flags: List[str] = []
    if p.get('enable_arc_fitting') == BOOL_TRUE:
        flags.append('Enable Arc Fitting')
    if p.get('enable_overhang_speed') == BOOL_TRUE:
        flags.append('Enable Overhang Speed')
    tt = p.get('timelapse_type')
    if tt and tt != '0':
        flags.append(f"Timelapse Type: {tt}")
    return f"[bright_cyan]{', '.join(flags)}[/bright_cyan]" if flags else ""


def _cond_features(p: Dict) -> bool:
    return bool(_fmt_features(p))


# ═══════════════════════════════════════════════════════════════
# GLOBAL_SETTINGS_FIELDS
# ═══════════════════════════════════════════════════════════════

GLOBAL_SETTINGS_FIELDS: List[Optional[FieldDef]] = [
    # -- Basic --
    ("Layer Height", "layer_height", _fmt_mm('layer_height'), None),
    ("Initial Layer Print Height", "initial_layer_print_height",
     _fmt_mm('initial_layer_print_height'), _if_present('initial_layer_print_height')),
    ("Line Width", "line_width", _fmt_mm('line_width'), _if_present('line_width')),
    (_flow_label, "print_flow_ratio", _fmt_flow_ratio, _has_flow),
    ("Wall Loops", "wall_loops", _fmt_plain('wall_loops'), None),
    ("Sparse Infill Density", "sparse_infill_density",
     _fmt_plain('sparse_infill_density'), None),
    ("Top/Bottom Shell Layers", "top_shell_layers", _fmt_shell_layers, None),
    ("Brim Type", "brim_type", _fmt_plain('brim_type'), None),
    ("Enable Support", "enable_support", _fmt_support_toggle, None),
    ("Seam Position", "seam_position", _fmt_plain('seam_position'), None),
    # -- Speeds --
    None,
    ("Initial Layer Speed", "initial_layer_speed",
     _fmt_speed('initial_layer_speed'), _if_present('initial_layer_speed')),
    ("Outer Wall Speed", "outer_wall_speed", _fmt_speed('outer_wall_speed'), None),
    ("Inner Wall Speed", "inner_wall_speed", _fmt_speed('inner_wall_speed'), None),
    ("Sparse Infill Speed", "sparse_infill_speed",
     _fmt_speed('sparse_infill_speed'), _if_present('sparse_infill_speed')),
    ("Top Surface Speed", "top_surface_speed",
     _fmt_speed('top_surface_speed'), _if_present('top_surface_speed')),
    ("Travel Speed", "travel_speed", _fmt_speed('travel_speed'), None),
    ("Bridge Speed", "bridge_speed", _fmt_speed('bridge_speed'), None),
    # -- Patterns --
    None,
    ("Sparse Infill Pattern", "sparse_infill_pattern",
     _fmt_plain('sparse_infill_pattern'), None),
    ("Top Surface Pattern", "top_surface_pattern",
     _fmt_plain('top_surface_pattern'), None),
    ("Print Sequence", "print_sequence", _fmt_plain('print_sequence'), None),
    ("Spiral Mode (Vase)", "spiral_mode", _fmt_spiral, _cond_spiral),
    ("Ironing Type", "ironing_type", _fmt_ironing, _cond_ironing),
    ("Fuzzy Skin", "fuzzy_skin", _fmt_fuzzy, _cond_fuzzy),
    # -- Retraction / Z-hop / PA / Fan / Cooling --
    None,
    ("Retraction Length", "retraction_length", _fmt_mm('retraction_length'), None),
    ("Retraction Speed", "retraction_speed",
     lambda p: f"{p.get('retraction_speed', '')} mm/s"
     if p.get('retraction_speed') else "",
     _if_present('retraction_speed')),
    ("Z-Hop", "z_hop", _fmt_mm('z_hop'), None),
    ("Pressure Advance", "pressure_advance",
     _fmt_plain('pressure_advance'), _if_present('pressure_advance')),
    ("Fan Min/Max Speed", "fan_min_speed", _fmt_fan, _cond_fan),
    ("Slow Down for Layer Cooling", "slow_down_for_layer_cooling",
     _fmt_cooling, _cond_cooling),
    # -- Temperatures --
    None,
    ("Nozzle Temperature", "nozzle_temperature",
     _fmt_temp('nozzle_temperature'), None),
    ("Bed Temperature", "bed_temperature",
     _fmt_temp('bed_temperature'), _if_present('bed_temperature')),
    # -- Features --
    None,
    ("[dim]Features[/dim]", "", _fmt_features, _cond_features),
]


# ═══════════════════════════════════════════════════════════════
# Statistics -- complex formatters
# ═══════════════════════════════════════════════════════════════

def _fmt_slicer(s: Dict) -> str:
    info = s.get('slicer', '')
    if info and s.get('slicer_version'):
        info += f" {s['slicer_version']}"
    return f"[cyan]{info}[/cyan]" if info else ""


def _fmt_file_size(s: Dict) -> str:
    b = s.get('file_size_bytes')
    if not b:
        return ""
    if b < 1024:
        return f"{b} B"
    elif b < 1024 * 1024:
        return f"{b / 1024:.1f} KB"
    return f"{b / (1024 * 1024):.2f} MB"


def _fmt_nozzle_diameter(s: Dict) -> str:
    nozzles = s.get('nozzle_diameter')
    if isinstance(nozzles, list) and nozzles:
        return f"{nozzles[0]} mm"
    return ""


def _cond_nozzle_diameter(s: Dict) -> bool:
    nozzles = s.get('nozzle_diameter')
    return isinstance(nozzles, list) and bool(nozzles)


def _fmt_filament_weight_total(s: Dict) -> str:
    v = s.get('filament_used_g')
    return f"[magenta]{v:.2f} g[/magenta]" if v else ""


def _fmt_filament_list(values: List[Any], suffix: str = '') -> str:
    """Format per-extruder filament values."""
    if not values:
        return ''
    if len(values) == 1:
        return f"{values[0]}{suffix}"
    return ', '.join(f"{v}{suffix}" for v in values)


def _fmt_filament_weight_per_ext(s: Dict) -> str:
    per_ext = s.get('filament_used_per_extruder_g')
    if per_ext:
        return _fmt_filament_list([f"{v:.2f}" for v in per_ext], ' g')
    return ""


def _fmt_filament_volume_per_ext(s: Dict) -> str:
    per_ext = s.get('filament_used_per_extruder_cm3')
    if per_ext:
        return _fmt_filament_list([f"{v:.2f}" for v in per_ext], ' cm3')
    return ""


def _fmt_filament_cost_total(s: Dict) -> str:
    v = s.get('filament_cost')
    if v and v > 0:
        return f"[gold1]${v:.2f}[/gold1]"
    return ""


def _cond_filament_cost_total(s: Dict) -> bool:
    v = s.get('filament_cost')
    return bool(v and v > 0)


def _fmt_filament_cost_per_ext(s: Dict) -> str:
    per_ext = s.get('filament_cost_per_extruder')
    if per_ext:
        formatted = _fmt_filament_list([f"${v:.2f}" for v in per_ext])
        return f"[gold1]{formatted}[/gold1]"
    return ""


def _fmt_filament_changes(s: Dict) -> str:
    v = s.get('filament_changes')
    if v and v > 0:
        return str(v)
    return ""


def _cond_filament_changes(s: Dict) -> bool:
    v = s.get('filament_changes')
    return bool(v and v > 0)


def _fmt_filament_vendor(s: Dict) -> str:
    vendors = s.get('filament_vendor')
    if vendors:
        filtered = [v for v in vendors if v]
        if filtered:
            return ', '.join(filtered)
    return ""


def _fmt_filament_types(s: Dict) -> str:
    types = s.get('filament_types')
    if types:
        filtered = [t for t in types if t]
        if filtered:
            return ', '.join(filtered)
    return ""


def _fmt_filament_density(s: Dict) -> str:
    density = s.get('filament_density')
    if isinstance(density, list) and density:
        return f"{density[0]} g/cm3"
    return ""


def _cond_filament_density(s: Dict) -> bool:
    density = s.get('filament_density')
    return isinstance(density, list) and bool(density)


def _fmt_filament_diameter(s: Dict) -> str:
    diameter = s.get('filament_diameter')
    if isinstance(diameter, list) and diameter:
        return f"{diameter[0]} mm"
    return ""


def _cond_filament_diameter(s: Dict) -> bool:
    diameter = s.get('filament_diameter')
    return isinstance(diameter, list) and bool(diameter)


def _fmt_prime_tower(s: Dict) -> str:
    v = s.get('enable_prime_tower', '')
    if v == '1':
        return "[green]On[/green]"
    elif v == '0':
        return "[dim]Off[/dim]"
    return str(v) if v else ""


def _fmt_nozzle_temp(s: Dict) -> str:
    temps = s.get('nozzle_temp')
    if isinstance(temps, list) and temps:
        return f"[red]{temps[0]}\u00b0C[/red]"
    return ""


def _cond_nozzle_temp(s: Dict) -> bool:
    temps = s.get('nozzle_temp')
    return isinstance(temps, list) and bool(temps)


# ═══════════════════════════════════════════════════════════════
# STATISTICS_FIELDS
# ═══════════════════════════════════════════════════════════════

STATISTICS_FIELDS: List[Optional[FieldDef]] = [
    # -- Slicer info --
    ("Slicer", "", _fmt_slicer, _if_present('slicer')),
    ("Generated", "", _fmt_plain('generated_date'), _if_present('generated_date')),
    ("File Size", "", _fmt_file_size, _if_present('file_size_bytes')),
    ("Printer Model", "", _fmt_plain('printer_model'), _if_present('printer_model')),
    ("G-code Flavor", "", _fmt_plain('gcode_flavor'), _if_present('gcode_flavor')),
    ("Nozzle Type", "", _fmt_plain('nozzle_type'), _if_present('nozzle_type')),
    ("Bed Type", "", _fmt_plain('curr_bed_type'), _if_present('curr_bed_type')),
    # -- Time estimates --
    None,
    ("Estimated Time", "", _fmt_green('estimated_time'), _if_present('estimated_time')),
    ("First Layer Time", "", _fmt_plain('estimated_first_layer_time'),
     _if_present('estimated_first_layer_time')),
    # -- Layer info --
    None,
    ("Total Layers", "", lambda s: str(s['total_layers']) if s.get('total_layers') else "",
     _if_present('total_layers')),
    ("Max Height", "", _fmt_mm('max_height'), _if_present('max_height')),
    ("Layer Height", "", _fmt_mm('layer_height'), _if_present('layer_height')),
    ("First Layer Height", "", _fmt_mm('first_layer_height'),
     _if_present('first_layer_height')),
    ("Nozzle Diameter", "", _fmt_nozzle_diameter, _cond_nozzle_diameter),
    # -- Filament usage --
    None,
    ("Filament Weight (Total)", "", _fmt_filament_weight_total,
     _if_present('filament_used_g')),
    ("Filament Weight Per Extruder", "", _fmt_filament_weight_per_ext,
     _if_present('filament_used_per_extruder_g')),
    ("Filament Volume Per Extruder", "", _fmt_filament_volume_per_ext,
     _if_present('filament_used_per_extruder_cm3')),
    ("Filament Cost (Total)", "", _fmt_filament_cost_total,
     _cond_filament_cost_total),
    ("Filament Cost Per Extruder", "", _fmt_filament_cost_per_ext,
     _if_present('filament_cost_per_extruder')),
    ("Filament Changes", "", _fmt_filament_changes, _cond_filament_changes),
    # -- Filament info (multi-row sentinels) --
    RENDER_FILAMENT_NAMES,
    ("Filament Vendor", "", _fmt_filament_vendor,
     _if_present('filament_vendor')),
    ("Filament Type", "", _fmt_filament_types, _if_present('filament_types')),
    RENDER_FILAMENT_COLORS,
    # -- Filament properties --
    ("Filament Density", "", _fmt_filament_density, _cond_filament_density),
    ("Filament Diameter", "", _fmt_filament_diameter, _cond_filament_diameter),
    ("Prime Tower", "", _fmt_prime_tower, _if_present('enable_prime_tower')),
    # -- Temperatures --
    None,
    ("First Layer Nozzle Temp", "", _fmt_temp('first_layer_nozzle_temp'),
     _if_present('first_layer_nozzle_temp')),
    ("Nozzle Temp", "", _fmt_nozzle_temp, _cond_nozzle_temp),
    ("First Layer Bed Temp", "", _fmt_temp('first_layer_bed_temp'),
     _if_present('first_layer_bed_temp')),
    ("Bed Temp", "", _fmt_temp('bed_temp'), _if_present('bed_temp')),
]
