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
from core.field_defs import (
    GLOBAL_SETTINGS_FIELDS,
    RENDER_FILAMENT_COLORS,
    RENDER_FILAMENT_NAMES,
    STATISTICS_FIELDS,
)

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

    json_path = Path(__file__).parent / "data" / "css3_colors.json"
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


def _render_fields_single(table: Table, fields, data: Dict[str, Any], wiki_label) -> None:
    """Render a field list into a single-column Rich Table.

    Shared loop used by both _print_global_settings and _print_statistics_panel.
    """
    for field in fields:
        if field is None:
            table.add_row("", "")
            continue
        label_or_fn, wiki_key, formatter, condition = field
        if condition and not condition(data):
            continue
        if callable(label_or_fn):
            label, wiki_key = label_or_fn(data)
            if not label:
                continue
        else:
            label = label_or_fn
        display_label = wiki_label(label, wiki_key) if wiki_key else label
        table.add_row(display_label, formatter(data))


def _print_global_settings(console: Console, profile: Dict[str, Any], wiki_label):
    gs = Table(show_header=False, box=None, padding=(0, 2))
    gs.add_column("Key", style="dim", width=SINGLE_LABEL_WIDTH)
    gs.add_column("Value", style="white")

    _render_fields_single(gs, GLOBAL_SETTINGS_FIELDS, profile, wiki_label)

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


def _render_stat_filament_names(table: Table, statistics: Dict[str, Any]) -> None:
    """Render filament name rows (one per extruder)."""
    names = statistics.get('filament_names')
    if not names:
        return
    for i, name in enumerate(names):
        if name:
            label = f"Filament {i + 1}" if len(names) > 1 else "Filament"
            table.add_row(label, f"[magenta]{name}[/magenta]")


def _render_stat_filament_colors(table: Table, statistics: Dict[str, Any]) -> None:
    """Render filament colors with hex blocks and CSS3 names."""
    colors = statistics.get('filament_colors')
    if not colors:
        return
    if isinstance(colors, list):
        styled = []
        for c in colors:
            name, style = _hex_to_color_name(c)
            styled.append(f"[{style}]\u2588\u2588[/{style}] {name}")
        color_display = ', '.join(styled)
    else:
        name, style = _hex_to_color_name(str(colors))
        color_display = f"[{style}]\u2588\u2588[/{style}] {name}"
    if color_display:
        table.add_row("Filament Colors", color_display)


def _print_statistics_panel(console: Console, statistics: Dict[str, Any]):
    """Print statistics panel for gcode analysis results."""
    if not statistics:
        return

    stats_table = Table(show_header=False, box=None, padding=(0, 2))
    stats_table.add_column("Key", style="dim", width=SINGLE_LABEL_WIDTH)
    stats_table.add_column("Value", style="white")

    for field in STATISTICS_FIELDS:
        if field is None:
            stats_table.add_row("", "")
            continue
        if field is RENDER_FILAMENT_NAMES:
            _render_stat_filament_names(stats_table, statistics)
            continue
        if field is RENDER_FILAMENT_COLORS:
            _render_stat_filament_colors(stats_table, statistics)
            continue
        label_or_fn, wiki_key, formatter, condition = field
        if condition and not condition(statistics):
            continue
        if callable(label_or_fn):
            label, wiki_key = label_or_fn(statistics)
            if not label:
                continue
        else:
            label = label_or_fn
        stats_table.add_row(label, formatter(statistics))

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
