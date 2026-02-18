"""Rich console output formatting for the 3MF Settings Analyzer."""

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from core.constants import BOOL_TRUE, FILAMENT_COLORS, PLATE_COLORS

logger = logging.getLogger(__name__)

SINGLE_LABEL_WIDTH = 31

# CSS3 named colors cache (loaded lazily from data/css3_colors.json)
_css3_colors_cache: Optional[Dict[str, List[int]]] = None


# ═══════════════════════════════════════════════════════════════
# Wiki helpers
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
        from core.settings_wiki import get_wiki_url
    except ImportError as e:
        logger.warning("Wiki module unavailable: %s. Wiki links disabled.", e)
        return (
            lambda display_name, setting_key: display_name,
            lambda setting_key: setting_key,
        )

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


# ═══════════════════════════════════════════════════════════════
# Color helpers
# ═══════════════════════════════════════════════════════════════

def _load_css3_colors() -> Dict[str, List[int]]:
    """Load CSS3 named colors from JSON data file (cached).

    Returns:
        Dict mapping color name (Title Case) to [R, G, B] list.
        Returns empty dict on load failure.
    """
    global _css3_colors_cache
    if _css3_colors_cache is not None:
        return _css3_colors_cache

    json_path = Path(__file__).parent.parent / "data" / "css3_colors.json"
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        _css3_colors_cache = data.get("colors", {})
    except (OSError, json.JSONDecodeError, KeyError) as e:
        logger.warning("Failed to load CSS3 colors from %s: %s", json_path, e)
        _css3_colors_cache = {}

    return _css3_colors_cache


def _find_nearest_css3_color(r: int, g: int, b: int) -> str:
    """Find the nearest CSS3 named color by Euclidean distance in RGB space.

    Args:
        r: Red component (0-255).
        g: Green component (0-255).
        b: Blue component (0-255).

    Returns:
        CSS3 color name in Title Case (e.g. "Goldenrod", "Crimson").
        Returns "Unknown" if no colors are loaded.
    """
    colors = _load_css3_colors()
    if not colors:
        return "Unknown"

    best_name = "Unknown"
    best_dist = float('inf')

    for name, rgb in colors.items():
        # Squared Euclidean distance (skip sqrt -- only need ordering)
        dist = (r - rgb[0]) ** 2 + (g - rgb[1]) ** 2 + (b - rgb[2]) ** 2
        if dist < best_dist:
            best_dist = dist
            best_name = name
            if dist == 0:
                break  # Exact match

    return best_name


def _hex_to_color_name(hex_color: str) -> Tuple[str, str]:
    """Convert hex color (#RRGGBBAA or #RRGGBB) to nearest CSS3 color name.

    Uses the W3C CSS Color Module Level 3 named colors (141 entries) and finds
    the nearest match by Euclidean distance in RGB space.

    The Rich style returned is the original hex code (supports 24-bit truecolor),
    giving exact color representation in the terminal.

    Args:
        hex_color: Hex color string like '#DE1619FF' or '#DE1619'.

    Returns:
        Tuple of (color_name, rich_hex_style) for terminal display.
        color_name is the nearest CSS3 color name (e.g. "Goldenrod").
        rich_hex_style is the original hex for Rich truecolor styling (e.g. "#DE1619").
    """
    if not hex_color or not hex_color.startswith('#'):
        return (hex_color, 'white')

    try:
        hex_str = hex_color[1:]
        if len(hex_str) >= 6:
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
        else:
            return (hex_color, 'white')

        color_name = _find_nearest_css3_color(r, g, b)
        # Use #RRGGBB (without alpha) as Rich style for truecolor display
        rich_style = f"#{hex_str[0:6]}"
        return (color_name, rich_style)

    except (ValueError, IndexError):
        return (hex_color, 'white')


# ═══════════════════════════════════════════════════════════════
# Formatting helpers
# ═══════════════════════════════════════════════════════════════

def _format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


def _format_filament_list(values: List[Any], suffix: str = '') -> str:
    """Format list of filament values (per extruder)."""
    if not values:
        return ''
    if len(values) == 1:
        return f"{values[0]}{suffix}"
    return ', '.join(f"{v}{suffix}" for v in values)


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
        return "Off"


# ═══════════════════════════════════════════════════════════════
# Panel / table rendering
# ═══════════════════════════════════════════════════════════════

def _print_header(console: Console, filename: str):
    table = Table(
        show_header=False, box=None,
        padding=(0, 2), expand=True,
    )
    table.add_column("", width=SINGLE_LABEL_WIDTH)
    table.add_column(ratio=1)
    table.add_row(
        "[bold bright_yellow]3MF SETTINGS ANALYZER:[/bold bright_yellow]",
        f"[bold white]{filename}[/bold white]",
    )
    console.print(Panel(table, border_style="dim bright_yellow"))


def _print_profile_panel(console: Console, profile: Dict[str, Any]):
    profile_table = Table(show_header=False, box=None, padding=(0, 2))
    profile_table.add_column("Key", style="dim", width=SINGLE_LABEL_WIDTH)
    profile_table.add_column("Value")

    profile_table.add_row("Printer", f"[white]{profile['printer']}[/white]")
    profile_table.add_row("Process", f"[green]{profile['process']}[/green]")

    filaments = profile['filaments']
    if isinstance(filaments, list):
        for i, f in enumerate(filaments):
            profile_table.add_row(f"Filament {i+1}", f"[magenta]{f}[/magenta]")

    console.rule("[bold bright_yellow]PROFILE[/bold bright_yellow]", style="grey50")
    console.print(Panel(profile_table, border_style="grey50", box=box.ROUNDED))


def _print_global_settings(console: Console, profile: Dict[str, Any], wiki_label):
    gs = Table(show_header=False, box=None, padding=(0, 2))
    gs.add_column("Key", style="dim", width=SINGLE_LABEL_WIDTH)
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

    console.rule("[bold bright_yellow]GLOBAL SETTINGS[/bold bright_yellow]", style="grey50")
    console.print(Panel(gs, border_style="grey50", box=box.ROUNDED))


def _print_custom_global(console: Console, custom: Dict[str, Any], wiki_key):
    if not custom:
        return
    custom_table = Table(show_header=False, box=None, padding=(0, 2))
    custom_table.add_column("Key", style="yellow", width=SINGLE_LABEL_WIDTH, no_wrap=True)
    custom_table.add_column("Value", style="white")
    for k, v in custom.items():
        custom_table.add_row(f"* {wiki_key(k)}", escape(str(v)))
    console.rule("[bold bright_yellow]CUSTOM GLOBAL SETTINGS[/bold bright_yellow] [bold bright_red](changed from profile)[/bold bright_red]",
                 style="grey50")
    console.print(Panel(custom_table, border_style="grey50", box=box.ROUNDED))


def _print_statistics_panel(console: Console, statistics: Dict[str, Any]):
    """Print statistics panel for gcode analysis results."""
    if not statistics:
        return

    stats_table = Table(show_header=False, box=None, padding=(0, 2))
    stats_table.add_column("Key", style="dim", width=SINGLE_LABEL_WIDTH)
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
        stats_table.add_row("Filament Cost (Total)", f"[gold1]${statistics['filament_cost']:.2f}[/gold1]")

    if statistics.get('filament_cost_per_extruder'):
        per_ext_cost = _format_filament_list(
            [f"${v:.2f}" for v in statistics['filament_cost_per_extruder']]
        )
        if per_ext_cost:
            stats_table.add_row("Filament Cost Per Extruder", f"[gold1]{per_ext_cost}[/gold1]")

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

    console.rule("[bold bright_yellow]STATISTICS[/bold bright_yellow]", style="grey50")
    console.print(Panel(stats_table, border_style="grey50", box=box.ROUNDED))


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


def _print_objects_table(console: Console, rows: List[Dict], profile: Dict[str, Any],
                         profile_full: Dict[str, Any], show_diff: bool, wiki_key):
    if not rows:
        console.print("\n[red]No objects found[/red]")
        return

    console.rule("[bold bright_yellow]OBJECTS[/bold bright_yellow]", style="grey50")

    table = Table(box=box.ROUNDED, show_lines=False, header_style="bold blue", expand=True, border_style="grey50",
                  row_styles=["", "on rgb(25,25,30)"])
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


# ═══════════════════════════════════════════════════════════════
# Public result printers
# ═══════════════════════════════════════════════════════════════

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

    # Use different header for gcode
    header_table = Table(
        show_header=False, box=box.SIMPLE, show_edge=False,
        padding=(0, 2), expand=True, border_style="dim bright_yellow",
    )
    header_table.add_column("", width=SINGLE_LABEL_WIDTH)
    header_table.add_column(ratio=1)
    header_table.add_row(
        "[bold bright_yellow]GCODE SETTINGS ANALYZER:[/bold bright_yellow]",
        f"[bold white]{result['file']}[/bold white]",
    )
    console.print(Panel(header_table, border_style="dim bright_yellow"))

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
