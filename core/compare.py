"""Comparison mode: side-by-side display for 2-4 files with diff highlighting."""

import logging
from typing import Any, Callable, Dict, List, Tuple

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.style import Style
from rich.table import Table
from rich.text import Text

from core.constants import BOOL_TRUE
from core.output import (
    _format_file_size,
    _format_filament_list,
    _hex_to_color_name,
    _make_wiki_helpers,
)

logger = logging.getLogger(__name__)

# Muted yellow background for differing values (industry standard, matches git diff / VS Code)
DIFF_BG = Style(bgcolor="rgb(80,60,10)")

LABEL_WIDTH = 34


# ═══════════════════════════════════════════════════════════════
# Table construction helpers
# ═══════════════════════════════════════════════════════════════

def _make_table(n_files: int, label_style: str = "dim") -> Table:
    """Create a comparison table with label column + N value columns."""
    table = Table(show_header=False, box=None, padding=(0, 2), expand=True)
    table.add_column("Setting", style=label_style, width=LABEL_WIDTH, no_wrap=True, overflow="ellipsis")
    for _ in range(n_files):
        table.add_column(ratio=1)
    return table


def _add_row(
    table: Table, label: str, values: List[str],
    placeholder: str = "",
) -> None:
    """Add a row with diff highlighting when values differ across files.

    Compares plain-text representation of values. When two or more distinct
    non-empty values exist, applies DIFF_BG background to every non-empty cell.

    Args:
        table: Rich Table to add the row to.
        label: Setting name (Rich markup string).
        values: List of value strings (Rich markup), one per file.
        placeholder: Rich markup to show for empty values (e.g. "[dim]--[/dim]").
    """
    plain = []
    for v in values:
        if v:
            plain.append(Text.from_markup(v).plain.strip())
        else:
            plain.append("")

    non_empty = [p for p in plain if p]
    if placeholder:
        differs = len(non_empty) > 0 and (
            len(set(non_empty)) > 1 or len(non_empty) < len(plain)
        )
    else:
        differs = len(set(non_empty)) > 1

    cells = []
    for v in values:
        if v:
            t = Text.from_markup(v)
            if differs:
                t.stylize(DIFF_BG)
        else:
            t = Text.from_markup(placeholder) if placeholder else Text("")
            if differs and placeholder:
                t.stylize(DIFF_BG)
        cells.append(t)

    table.add_row(label, *cells)


def _add_separator(table: Table, n_files: int) -> None:
    """Add an empty separator row."""
    table.add_row("", *[""] * n_files)


# ═══════════════════════════════════════════════════════════════
# Section renderers
# ═══════════════════════════════════════════════════════════════

def _print_compare_header(
    console: Console, filenames: List[str], is_gcode: bool,
) -> None:
    """Print the comparison title panel with file names aligned to columns."""
    title = "GCODE" if is_gcode else "3MF"
    table = Table(
        show_header=False, box=None,
        padding=(0, 2), expand=True,
    )
    table.add_column("", width=LABEL_WIDTH)
    for _ in filenames:
        table.add_column(ratio=1)
    table.add_row(
        f"[bold bright_yellow]{title} SETTINGS COMPARISON:[/bold bright_yellow]",
        *[f"[bold white]{name}[/bold white]" for name in filenames],
    )
    console.print(Panel(table, border_style="dim bright_yellow"))


def _print_compare_profile(
    console: Console, results: List[Dict], n: int,
) -> None:
    """Print Profile section (Printer, Process, Filaments) with columns."""
    profiles = [r['profile'] for r in results]
    table = _make_table(n)

    _add_row(table, "Printer",
             [f"[white]{p['printer']}[/white]" for p in profiles])
    _add_row(table, "Process",
             [f"[green]{p['process']}[/green]" for p in profiles])

    max_fil = max(
        len(p['filaments']) if isinstance(p['filaments'], list) else 1
        for p in profiles
    )
    for i in range(max_fil):
        values = []
        for p in profiles:
            fils = p['filaments']
            if isinstance(fils, list) and i < len(fils):
                values.append(f"[magenta]{fils[i]}[/magenta]")
            elif not isinstance(fils, list) and i == 0:
                values.append(f"[magenta]{fils}[/magenta]")
            else:
                values.append("")
        _add_row(table, f"Filament {i + 1}", values)

    console.rule("[bold bright_yellow]PROFILE[/bold bright_yellow]", style="grey50")
    console.print(Panel(table, border_style="grey50", box=box.ROUNDED))


# ── Global Settings helpers ──────────────────────────────────

def _get_flow_value(profile: Dict) -> Tuple[str, str]:
    """Extract flow ratio display name and formatted value from a profile."""
    if profile.get('print_flow_ratio') and profile['print_flow_ratio'] != '1':
        try:
            flow_pct = f"{float(profile['print_flow_ratio']) * 100:.0f}%"
        except (ValueError, TypeError):
            flow_pct = str(profile['print_flow_ratio'])
        return ("Print Flow Ratio", flow_pct)
    elif profile.get('filament_flow_ratio'):
        return ("Filament Flow Ratio", profile['filament_flow_ratio'])
    return ("", "")


def _get_features(profile: Dict) -> str:
    """Build Rich-markup features string for a profile."""
    flags = []
    if profile.get('enable_arc_fitting') == BOOL_TRUE:
        flags.append('Enable Arc Fitting')
    if profile.get('enable_overhang_speed') == BOOL_TRUE:
        flags.append('Enable Overhang Speed')
    tt = profile.get('timelapse_type')
    if tt and tt != '0':
        flags.append(f"Timelapse Type: {tt}")
    if flags:
        return f"[bright_cyan]{', '.join(flags)}[/bright_cyan]"
    return ""


def _print_compare_global_settings(
    console: Console, results: List[Dict], n: int, wiki_label: Callable,
) -> None:
    """Print Global Settings section with columns and diff highlighting.

    Replicates every subsection (Basic, Speeds, Patterns, Retraction,
    Temps, Features) from output.py._print_global_settings.
    """
    profiles = [r['profile'] for r in results]
    table = _make_table(n)

    # -- Basic --
    _add_row(table, wiki_label("Layer Height", "layer_height"),
             [f"{p['layer_height']} mm" for p in profiles])

    if any(p.get('initial_layer_print_height') for p in profiles):
        _add_row(
            table, wiki_label("Initial Layer Print Height", "initial_layer_print_height"),
            [f"{p['initial_layer_print_height']} mm"
             if p.get('initial_layer_print_height') else "" for p in profiles],
        )

    if any(p.get('line_width') for p in profiles):
        _add_row(
            table, wiki_label("Line Width", "line_width"),
            [f"{p['line_width']} mm" if p.get('line_width') else "" for p in profiles],
        )

    flow_data = [_get_flow_value(p) for p in profiles]
    if any(v for _, v in flow_data):
        label_name = next((name for name, _ in flow_data if name), "Flow Ratio")
        setting_key = "print_flow_ratio" if "Print" in label_name else "filament_flow_ratio"
        _add_row(table, wiki_label(label_name, setting_key),
                 [v if v else "" for _, v in flow_data])

    _add_row(table, wiki_label("Wall Loops", "wall_loops"),
             [p['wall_loops'] for p in profiles])

    _add_row(table, wiki_label("Sparse Infill Density", "sparse_infill_density"),
             [p['sparse_infill_density'] for p in profiles])

    _add_row(table, wiki_label("Top/Bottom Shell Layers", "top_shell_layers"),
             [f"{p['top_shell_layers']}/{p['bottom_shell_layers']}" for p in profiles])

    _add_row(table, wiki_label("Brim Type", "brim_type"),
             [p['brim_type'] for p in profiles])

    _add_row(table, wiki_label("Enable Support", "enable_support"),
             ["On" if p['enable_support'] == BOOL_TRUE else "Off" for p in profiles])

    _add_row(table, wiki_label("Seam Position", "seam_position"),
             [p['seam_position'] for p in profiles])

    # -- Speeds --
    _add_separator(table, n)

    if any(p.get('initial_layer_speed') for p in profiles):
        _add_row(
            table, wiki_label("Initial Layer Speed", "initial_layer_speed"),
            [f"[cyan]{p['initial_layer_speed']} mm/s[/cyan]"
             if p.get('initial_layer_speed') else "" for p in profiles],
        )

    _add_row(table, wiki_label("Outer Wall Speed", "outer_wall_speed"),
             [f"[cyan]{p['outer_wall_speed']} mm/s[/cyan]" for p in profiles])

    _add_row(table, wiki_label("Inner Wall Speed", "inner_wall_speed"),
             [f"[cyan]{p['inner_wall_speed']} mm/s[/cyan]" for p in profiles])

    if any(p.get('sparse_infill_speed') for p in profiles):
        _add_row(
            table, wiki_label("Sparse Infill Speed", "sparse_infill_speed"),
            [f"[cyan]{p['sparse_infill_speed']} mm/s[/cyan]"
             if p.get('sparse_infill_speed') else "" for p in profiles],
        )

    if any(p.get('top_surface_speed') for p in profiles):
        _add_row(
            table, wiki_label("Top Surface Speed", "top_surface_speed"),
            [f"[cyan]{p['top_surface_speed']} mm/s[/cyan]"
             if p.get('top_surface_speed') else "" for p in profiles],
        )

    _add_row(table, wiki_label("Travel Speed", "travel_speed"),
             [f"[cyan]{p['travel_speed']} mm/s[/cyan]" for p in profiles])

    _add_row(table, wiki_label("Bridge Speed", "bridge_speed"),
             [f"[cyan]{p['bridge_speed']} mm/s[/cyan]" for p in profiles])

    # -- Patterns --
    _add_separator(table, n)

    _add_row(table, wiki_label("Sparse Infill Pattern", "sparse_infill_pattern"),
             [p['sparse_infill_pattern'] for p in profiles])

    _add_row(table, wiki_label("Top Surface Pattern", "top_surface_pattern"),
             [p['top_surface_pattern'] for p in profiles])

    _add_row(table, wiki_label("Print Sequence", "print_sequence"),
             [p['print_sequence'] for p in profiles])

    if any(p.get('spiral_mode') == BOOL_TRUE for p in profiles):
        _add_row(
            table, wiki_label("Spiral Mode (Vase)", "spiral_mode"),
            ["[bright_green]ON[/bright_green]"
             if p.get('spiral_mode') == BOOL_TRUE else "[dim]Off[/dim]"
             for p in profiles],
        )

    if any(p.get('ironing_type') and p['ironing_type'] not in ('no ironing', 'no_ironing')
           for p in profiles):
        _add_row(
            table, wiki_label("Ironing Type", "ironing_type"),
            [f"[bright_green]{p['ironing_type']}[/bright_green]"
             if p.get('ironing_type') and p['ironing_type'] not in ('no ironing', 'no_ironing')
             else "" for p in profiles],
        )

    if any(p.get('fuzzy_skin') and p['fuzzy_skin'] != 'none' for p in profiles):
        _add_row(
            table, wiki_label("Fuzzy Skin", "fuzzy_skin"),
            [f"[bright_green]{p['fuzzy_skin']}[/bright_green]"
             if p.get('fuzzy_skin') and p['fuzzy_skin'] != 'none'
             else "" for p in profiles],
        )

    # -- Retraction / Z-hop / PA / Fan / Cooling --
    _add_separator(table, n)

    _add_row(table, wiki_label("Retraction Length", "retraction_length"),
             [f"{p['retraction_length']} mm" for p in profiles])

    if any(p.get('retraction_speed') for p in profiles):
        _add_row(
            table, wiki_label("Retraction Speed", "retraction_speed"),
            [f"{p['retraction_speed']} mm/s"
             if p.get('retraction_speed') else "" for p in profiles],
        )

    _add_row(table, wiki_label("Z-Hop", "z_hop"),
             [f"{p['z_hop']} mm" for p in profiles])

    if any(p.get('pressure_advance') for p in profiles):
        _add_row(
            table, wiki_label("Pressure Advance", "pressure_advance"),
            [p['pressure_advance'] if p.get('pressure_advance') else ""
             for p in profiles],
        )

    if any(p.get('fan_min_speed') or p.get('fan_max_speed') for p in profiles):
        _add_row(
            table, wiki_label("Fan Min/Max Speed", "fan_min_speed"),
            [f"{p.get('fan_min_speed', '')}% / {p.get('fan_max_speed', '')}%"
             if p.get('fan_min_speed') or p.get('fan_max_speed') else ""
             for p in profiles],
        )

    if any(p.get('slow_down_for_layer_cooling') for p in profiles):
        vals = []
        for p in profiles:
            if p.get('slow_down_for_layer_cooling') == BOOL_TRUE:
                vals.append(f"[green]On[/green] ({p.get('slow_down_layer_time', '')}s)")
            elif p.get('slow_down_for_layer_cooling'):
                vals.append("[dim]Off[/dim]")
            else:
                vals.append("")
        _add_row(table, wiki_label("Slow Down for Layer Cooling", "slow_down_for_layer_cooling"), vals)

    # -- Temperatures --
    _add_separator(table, n)

    _add_row(table, wiki_label("Nozzle Temperature", "nozzle_temperature"),
             [f"[red]{p['nozzle_temperature']}°C[/red]" for p in profiles])

    if any(p.get('bed_temperature') for p in profiles):
        _add_row(
            table, wiki_label("Bed Temperature", "bed_temperature"),
            [f"[red]{p['bed_temperature']}°C[/red]"
             if p.get('bed_temperature') else "" for p in profiles],
        )

    # -- Features --
    feature_values = [_get_features(p) for p in profiles]
    if any(feature_values):
        _add_separator(table, n)
        _add_row(table, "[dim]Features[/dim]", feature_values)

    console.rule("[bold bright_yellow]GLOBAL SETTINGS[/bold bright_yellow]", style="grey50")
    console.print(Panel(table, border_style="grey50", box=box.ROUNDED))


def _print_compare_custom_global(
    console: Console, results: List[Dict], n: int, wiki_key: Callable,
) -> None:
    """Print Custom Global Settings section with columns.

    Shows the union of all custom keys across files with diff highlighting.
    """
    customs = [r.get('custom_global', {}) for r in results]

    all_keys: List[str] = []
    seen: set = set()
    for c in customs:
        for k in c:
            if k not in seen:
                all_keys.append(k)
                seen.add(k)

    if not all_keys:
        return

    table = _make_table(n, label_style="yellow")

    for key in all_keys:
        values = []
        for c in customs:
            val = c.get(key)
            values.append(escape(str(val)) if val is not None else "")
        _add_row(table, f"* {wiki_key(key)}", values, placeholder="[dim]--[/dim]")

    console.rule(
        "[bold bright_yellow]CUSTOM GLOBAL SETTINGS[/bold bright_yellow] "
        "[bold bright_red](changed from profile)[/bold bright_red]",
        style="grey50",
    )
    console.print(Panel(table, border_style="grey50", box=box.ROUNDED))


def _print_compare_objects_gcode(
    console: Console, results: List[Dict], n: int,
) -> None:
    """Print Objects section for gcode comparison (per-file object lists in table)."""
    objects_per_file = [r.get('objects', []) for r in results]
    max_count = max((len(objs) for objs in objects_per_file), default=0)

    if max_count == 0:
        console.print("\n[red]No objects found[/red]")
        return

    console.rule("[bold bright_yellow]OBJECTS[/bold bright_yellow]", style="grey50")
    filenames = [r['file'] for r in results]
    _print_objects_compare_table(console, objects_per_file, filenames)


def _resolve_object_name(
    parents_per_file: List[List[Dict]], obj_idx: int,
) -> str:
    """Pick the first non-empty object name across files for a given index."""
    for plist in parents_per_file:
        if obj_idx < len(plist):
            return plist[obj_idx].get('name', f'Object {obj_idx + 1}').strip()
    return f"Object {obj_idx + 1}"


def _resolve_child_name(
    children_per_file: List[List[Dict]], child_idx: int,
) -> str:
    """Pick the first non-empty child name across files for a given index."""
    for ch in children_per_file:
        if child_idx < len(ch):
            return ch[child_idx].get('name', 'Part').strip()
    return "Part"


def _collect_children(
    all_rows: List[List[Dict]],
    parents_per_file: List[List[Dict]],
    obj_idx: int,
) -> List[List[Dict]]:
    """Collect child (part) rows that follow a given parent object in each file."""
    children_per_file: List[List[Dict]] = []
    for file_idx, rows in enumerate(all_rows):
        plist = parents_per_file[file_idx]
        if obj_idx >= len(plist):
            children_per_file.append([])
            continue

        parent_pos = rows.index(plist[obj_idx])
        children: List[Dict] = []
        for row in rows[parent_pos + 1:]:
            if row.get('is_parent'):
                break
            children.append(row)
        children_per_file.append(children)
    return children_per_file


def _add_object_setting_rows(
    table: Table,
    obj_rows: List[Any],
    n: int,
    settings: List[Tuple[str, str]],
    indent: str = "  ",
) -> None:
    """Add standard setting rows for one object across files."""
    for label, key in settings:
        values = []
        for row in obj_rows:
            if row is None:
                values.append("")
            else:
                val = row.get(key, "")
                values.append(str(val) if val else "")
        _add_row(table, f"[bold blue]{indent}{label}[/bold blue]", values, placeholder="[dim]--[/dim]")


def _add_object_custom_rows(
    table: Table,
    obj_rows: List[Any],
    n: int,
    indent: str = "  ",
) -> None:
    """Add custom per-object settings as union rows with diff highlighting."""
    customs = [
        (row.get('custom_settings', {}) if row else {})
        for row in obj_rows
    ]
    all_keys: List[str] = []
    seen: set = set()
    for c in customs:
        for k in c:
            if k not in seen:
                all_keys.append(k)
                seen.add(k)

    for key in all_keys:
        values = []
        for c in customs:
            val = c.get(key)
            values.append(escape(str(val)) if val is not None else "")
        _add_row(
            table,
            f"[yellow]{indent}└─ * {key}[/yellow]",
            values,
            placeholder="[dim]--[/dim]",
        )


def _add_obj_bordered_rows(
    table: Table,
    obj_rows: List[Any],
    n: int,
    settings: List[Tuple[str, str]],
    indent: str = "  ",
) -> None:
    """Add standard setting rows to a bordered objects table with diff highlighting."""
    for label, key in settings:
        values = []
        for row in obj_rows:
            if row is None:
                values.append("")
            else:
                val = row.get(key, "")
                values.append(str(val) if val else "")

        non_empty = [v for v in values if v]
        differs = (
            len(non_empty) > 0
            and (len(set(non_empty)) > 1 or len(non_empty) < len(values))
        )

        cells = []
        for v in values:
            if v:
                t = Text(v)
                if differs:
                    t.stylize(DIFF_BG)
            else:
                t = Text.from_markup("[dim]--[/dim]")
                if differs:
                    t.stylize(DIFF_BG)
            cells.append(t)
        table.add_row(f"[bold blue]{indent}{label}[/bold blue]", *cells)


def _add_obj_bordered_custom(
    table: Table,
    obj_rows: List[Any],
    n: int,
    indent: str = "  ",
) -> None:
    """Add custom per-object settings to a bordered objects table with diff highlighting."""
    customs = [
        (row.get('custom_settings', {}) if row else {})
        for row in obj_rows
    ]
    all_keys: List[str] = []
    seen: set = set()
    for c in customs:
        for k in c:
            if k not in seen:
                all_keys.append(k)
                seen.add(k)

    for key in all_keys:
        values = []
        for c in customs:
            val = c.get(key)
            values.append(str(val) if val is not None else "")

        non_empty = [v for v in values if v]
        differs = (
            len(non_empty) > 0
            and (len(set(non_empty)) > 1 or len(non_empty) < len(values))
        )

        cells = []
        for v in values:
            if v:
                t = Text(v)
                if differs:
                    t.stylize(DIFF_BG)
            else:
                t = Text.from_markup("[dim]--[/dim]")
                if differs:
                    t.stylize(DIFF_BG)
            cells.append(t)
        table.add_row(f"[yellow]{indent}\u2514\u2500 * {key}[/yellow]", *cells)


def _print_compare_objects_3mf(
    console: Console, results: List[Dict], n: int,
) -> None:
    """Print Objects section for 3MF comparison (transposed with bordered table)."""
    all_rows = [r.get('rows', []) for r in results]

    parents_per_file = [
        [row for row in rows if row.get('is_parent')]
        for rows in all_rows
    ]
    max_parents = max((len(p) for p in parents_per_file), default=0)

    if max_parents == 0:
        console.print("\n[red]No objects found[/red]")
        return

    console.rule("[bold bright_yellow]OBJECTS[/bold bright_yellow]", style="grey50")

    filenames = [r['file'] for r in results]
    table = Table(
        box=box.ROUNDED, show_lines=False, header_style="bold blue",
        expand=True, border_style="grey50",
        row_styles=["", "on rgb(25,25,30)"],
    )
    table.add_column("Setting", width=LABEL_WIDTH, no_wrap=True)
    for _ in filenames:
        table.add_column("Value", ratio=1)

    _OBJ_SETTINGS = [
        ("Plate", "plate"),
        ("Filament", "filament"),
        ("Layer Height", "layer_height"),
        ("Wall Loops", "wall_loops"),
        ("Infill Density", "infill"),
        ("Support", "support"),
        ("Brim Type", "brim"),
        ("Outer Wall Speed", "outer_wall_speed"),
    ]

    _CHILD_SETTINGS = [
        ("Filament", "filament"),
        ("Wall Loops", "wall_loops"),
        ("Infill Density", "infill"),
        ("Support", "support"),
        ("Outer Wall Speed", "outer_wall_speed"),
    ]

    for obj_idx in range(max_parents):
        if obj_idx > 0:
            table.add_section()

        obj_name = _resolve_object_name(parents_per_file, obj_idx)
        table.add_row(
            f"[bold white]#{obj_idx + 1}  {escape(obj_name)}[/bold white]",
            *[""] * n,
        )

        parent_rows = [
            plist[obj_idx] if obj_idx < len(plist) else None
            for plist in parents_per_file
        ]

        _add_obj_bordered_rows(table, parent_rows, n, _OBJ_SETTINGS)
        _add_obj_bordered_custom(table, parent_rows, n)

        children_per_file = _collect_children(all_rows, parents_per_file, obj_idx)
        max_children = max((len(ch) for ch in children_per_file), default=0)

        for child_idx in range(max_children):
            child_name = _resolve_child_name(children_per_file, child_idx)
            table.add_row(
                f"  [dim]{escape(child_name)}[/dim]",
                *[""] * n,
            )
            child_rows = [
                ch[child_idx] if child_idx < len(ch) else None
                for ch in children_per_file
            ]
            _add_obj_bordered_rows(table, child_rows, n, _CHILD_SETTINGS, indent="    ")
            _add_obj_bordered_custom(table, child_rows, n, indent="    ")

    console.print(table)
    console.print("[bold yellow]*[/bold yellow] = custom value (overrides profile default)")


def _print_objects_compare_table(
    console: Console, names_per_file: List[List[str]], filenames: List[str],
) -> None:
    """Render a bordered objects table with per-file columns (same style as single-file)."""
    max_count = max((len(names) for names in names_per_file), default=0)

    table = Table(
        box=box.ROUNDED, show_lines=False, header_style="bold blue",
        expand=True, border_style="grey50",
    )
    table.add_column("#", justify="center", style="dim", width=LABEL_WIDTH)
    for _ in filenames:
        table.add_column("Name", style="white", ratio=1)

    for i in range(max_count):
        plain_vals = []
        markup_vals = []
        for names in names_per_file:
            if i < len(names):
                plain_vals.append(names[i])
                markup_vals.append(f"[bold white]{escape(names[i])}[/bold white]")
            else:
                plain_vals.append("")
                markup_vals.append("")

        non_empty = [v for v in plain_vals if v]
        differs = (
            len(non_empty) > 0
            and (len(set(non_empty)) > 1 or len(non_empty) < len(plain_vals))
        )

        cells = []
        for m in markup_vals:
            if m:
                t = Text.from_markup(m)
                if differs:
                    t.stylize(DIFF_BG)
            else:
                t = Text.from_markup("[dim]--[/dim]")
                if differs:
                    t.stylize(DIFF_BG)
            cells.append(t)
        table.add_row(str(i + 1), *cells)

    console.print(table)


# ── Statistics helpers ───────────────────────────────────────

def _format_stat_filament_colors(statistics: Dict) -> str:
    """Format filament colors with color blocks for a single file's statistics."""
    colors = statistics.get('filament_colors')
    if not colors:
        return ""
    if isinstance(colors, list):
        styled = []
        for c in colors:
            name, style = _hex_to_color_name(c)
            styled.append(f"[{style}]██[/{style}] {name}")
        return ', '.join(styled)
    name, style = _hex_to_color_name(str(colors))
    return f"[{style}]██[/{style}] {name}"


def _print_compare_statistics(
    console: Console, results: List[Dict], n: int,
) -> None:
    """Print Statistics section for gcode comparison with columns."""
    stats_list = [r.get('statistics', {}) for r in results]
    if not any(stats_list):
        return

    table = _make_table(n)

    # -- Slicer info --
    if any(s.get('slicer') for s in stats_list):
        vals = []
        for s in stats_list:
            info = s.get('slicer', '')
            if info and s.get('slicer_version'):
                info += f" {s['slicer_version']}"
            vals.append(f"[cyan]{info}[/cyan]" if info else "")
        _add_row(table, "Slicer", vals)

    if any(s.get('generated_date') for s in stats_list):
        _add_row(table, "Generated",
                 [s.get('generated_date', '') for s in stats_list])

    if any(s.get('file_size_bytes') for s in stats_list):
        _add_row(table, "File Size",
                 [_format_file_size(s['file_size_bytes'])
                  if s.get('file_size_bytes') else "" for s in stats_list])

    if any(s.get('printer_model') for s in stats_list):
        _add_row(table, "Printer Model",
                 [s.get('printer_model', '') for s in stats_list])

    if any(s.get('gcode_flavor') for s in stats_list):
        _add_row(table, "G-code Flavor",
                 [s.get('gcode_flavor', '') for s in stats_list])

    if any(s.get('nozzle_type') for s in stats_list):
        _add_row(table, "Nozzle Type",
                 [s.get('nozzle_type', '') for s in stats_list])

    if any(s.get('curr_bed_type') for s in stats_list):
        _add_row(table, "Bed Type",
                 [s.get('curr_bed_type', '') for s in stats_list])

    # -- Time estimates --
    _add_separator(table, n)

    if any(s.get('estimated_time') for s in stats_list):
        _add_row(table, "Estimated Time",
                 [f"[green]{s['estimated_time']}[/green]"
                  if s.get('estimated_time') else "" for s in stats_list])

    if any(s.get('estimated_first_layer_time') for s in stats_list):
        _add_row(table, "First Layer Time",
                 [s.get('estimated_first_layer_time', '') for s in stats_list])

    # -- Layer info --
    _add_separator(table, n)

    if any(s.get('total_layers') for s in stats_list):
        _add_row(table, "Total Layers",
                 [str(s['total_layers']) if s.get('total_layers') else ""
                  for s in stats_list])

    if any(s.get('max_height') for s in stats_list):
        _add_row(table, "Max Height",
                 [f"{s['max_height']} mm" if s.get('max_height') else ""
                  for s in stats_list])

    if any(s.get('layer_height') for s in stats_list):
        _add_row(table, "Layer Height",
                 [f"{s['layer_height']} mm" if s.get('layer_height') else ""
                  for s in stats_list])

    if any(s.get('first_layer_height') for s in stats_list):
        _add_row(table, "First Layer Height",
                 [f"{s['first_layer_height']} mm" if s.get('first_layer_height') else ""
                  for s in stats_list])

    if any(s.get('nozzle_diameter') for s in stats_list):
        vals = []
        for s in stats_list:
            nozzles = s.get('nozzle_diameter', [])
            if isinstance(nozzles, list) and nozzles:
                vals.append(f"{nozzles[0]} mm")
            else:
                vals.append("")
        _add_row(table, "Nozzle Diameter", vals)

    # -- Filament usage --
    _add_separator(table, n)

    if any(s.get('filament_used_g') for s in stats_list):
        _add_row(table, "Filament Weight (Total)",
                 [f"[magenta]{s['filament_used_g']:.2f} g[/magenta]"
                  if s.get('filament_used_g') else "" for s in stats_list])

    if any(s.get('filament_used_per_extruder_g') for s in stats_list):
        vals = []
        for s in stats_list:
            per_ext = s.get('filament_used_per_extruder_g', [])
            if per_ext:
                vals.append(_format_filament_list(
                    [f"{v:.2f}" for v in per_ext], ' g'))
            else:
                vals.append("")
        _add_row(table, "Filament Weight Per Extruder", vals)

    if any(s.get('filament_used_per_extruder_cm3') for s in stats_list):
        vals = []
        for s in stats_list:
            per_ext = s.get('filament_used_per_extruder_cm3', [])
            if per_ext:
                vals.append(_format_filament_list(
                    [f"{v:.2f}" for v in per_ext], ' cm3'))
            else:
                vals.append("")
        _add_row(table, "Filament Volume Per Extruder", vals)

    if any(s.get('filament_cost') and s['filament_cost'] > 0 for s in stats_list):
        _add_row(table, "Filament Cost (Total)",
                 [f"[gold1]${s['filament_cost']:.2f}[/gold1]"
                  if s.get('filament_cost') and s['filament_cost'] > 0 else ""
                  for s in stats_list])

    if any(s.get('filament_cost_per_extruder') for s in stats_list):
        vals = []
        for s in stats_list:
            per_ext = s.get('filament_cost_per_extruder', [])
            if per_ext:
                formatted = _format_filament_list([f"${v:.2f}" for v in per_ext])
                vals.append(f"[gold1]{formatted}[/gold1]")
            else:
                vals.append("")
        _add_row(table, "Filament Cost Per Extruder", vals)

    if any(s.get('filament_changes') and s['filament_changes'] > 0
           for s in stats_list):
        _add_row(table, "Filament Changes",
                 [str(s['filament_changes'])
                  if s.get('filament_changes') and s['filament_changes'] > 0 else ""
                  for s in stats_list])

    # -- Filament info --
    if any(s.get('filament_names') for s in stats_list):
        max_fils = max(
            (len(s.get('filament_names', [])) for s in stats_list), default=0)
        for i in range(max_fils):
            label = f"Filament {i + 1}" if max_fils > 1 else "Filament"
            vals = []
            for s in stats_list:
                names = s.get('filament_names', [])
                if i < len(names) and names[i]:
                    vals.append(f"[magenta]{names[i]}[/magenta]")
                else:
                    vals.append("")
            _add_row(table, label, vals)

    if any(s.get('filament_vendor') for s in stats_list):
        vals = []
        for s in stats_list:
            vendors = [v for v in s.get('filament_vendor', []) if v]
            vals.append(', '.join(vendors) if vendors else "")
        _add_row(table, "Filament Vendor", vals)

    if any(s.get('filament_types') for s in stats_list):
        vals = []
        for s in stats_list:
            types = [t for t in s.get('filament_types', []) if t]
            vals.append(', '.join(types) if types else "")
        _add_row(table, "Filament Type", vals)

    if any(s.get('filament_colors') for s in stats_list):
        _add_row(table, "Filament Colors",
                 [_format_stat_filament_colors(s) for s in stats_list])

    if any(s.get('filament_density') for s in stats_list):
        vals = []
        for s in stats_list:
            density = s.get('filament_density', [])
            if isinstance(density, list) and density:
                vals.append(f"{density[0]} g/cm3")
            else:
                vals.append("")
        _add_row(table, "Filament Density", vals)

    if any(s.get('filament_diameter') for s in stats_list):
        vals = []
        for s in stats_list:
            diameter = s.get('filament_diameter', [])
            if isinstance(diameter, list) and diameter:
                vals.append(f"{diameter[0]} mm")
            else:
                vals.append("")
        _add_row(table, "Filament Diameter", vals)

    if any(s.get('enable_prime_tower') for s in stats_list):
        vals = []
        for s in stats_list:
            prime_val = s.get('enable_prime_tower', '')
            if prime_val == '1':
                vals.append("[green]On[/green]")
            elif prime_val == '0':
                vals.append("[dim]Off[/dim]")
            elif prime_val:
                vals.append(prime_val)
            else:
                vals.append("")
        _add_row(table, "Prime Tower", vals)

    # -- Temperatures --
    _add_separator(table, n)

    if any(s.get('first_layer_nozzle_temp') for s in stats_list):
        _add_row(table, "First Layer Nozzle Temp",
                 [f"[red]{s['first_layer_nozzle_temp']}°C[/red]"
                  if s.get('first_layer_nozzle_temp') else ""
                  for s in stats_list])

    if any(s.get('nozzle_temp') for s in stats_list):
        vals = []
        for s in stats_list:
            temps = s.get('nozzle_temp', [])
            if isinstance(temps, list) and temps:
                vals.append(f"[red]{temps[0]}°C[/red]")
            else:
                vals.append("")
        _add_row(table, "Nozzle Temp", vals)

    if any(s.get('first_layer_bed_temp') for s in stats_list):
        _add_row(table, "First Layer Bed Temp",
                 [f"[red]{s['first_layer_bed_temp']}°C[/red]"
                  if s.get('first_layer_bed_temp') else ""
                  for s in stats_list])

    if any(s.get('bed_temp') for s in stats_list):
        _add_row(table, "Bed Temp",
                 [f"[red]{s['bed_temp']}°C[/red]"
                  if s.get('bed_temp') else "" for s in stats_list])

    console.rule("[bold bright_yellow]STATISTICS[/bold bright_yellow]", style="grey50")
    console.print(Panel(table, border_style="grey50", box=box.ROUNDED))


# ═══════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════

def print_gcode_comparison(
    results: List[Dict[str, Any]],
    no_color: bool = False,
    wiki: bool = False,
) -> None:
    """Render side-by-side comparison for 2-4 gcode files.

    Args:
        results: List of parsed gcode result dicts.
        no_color: Disable colored output.
        wiki: Add clickable wiki links to setting names.
    """
    wiki_label, wiki_key = _make_wiki_helpers(wiki)
    console = Console(no_color=no_color)
    n = len(results)
    filenames = [r['file'] for r in results]

    _print_compare_header(console, filenames, is_gcode=True)
    _print_compare_profile(console, results, n)
    _print_compare_global_settings(console, results, n, wiki_label)
    _print_compare_custom_global(console, results, n, wiki_key)
    _print_compare_objects_gcode(console, results, n)
    _print_compare_statistics(console, results, n)


def print_3mf_comparison(
    results: List[Dict[str, Any]],
    show_diff: bool = False,
    no_color: bool = False,
    wiki: bool = False,
) -> None:
    """Render side-by-side comparison for 2-4 3MF files.

    Args:
        results: List of parsed 3MF result dicts.
        show_diff: Show comparison with profile defaults.
        no_color: Disable colored output.
        wiki: Add clickable wiki links to setting names.
    """
    wiki_label, wiki_key = _make_wiki_helpers(wiki)
    console = Console(no_color=no_color)
    n = len(results)
    filenames = [r['file'] for r in results]

    _print_compare_header(console, filenames, is_gcode=False)
    _print_compare_profile(console, results, n)
    _print_compare_global_settings(console, results, n, wiki_label)
    _print_compare_custom_global(console, results, n, wiki_key)
    _print_compare_objects_3mf(console, results, n)
