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
from core.field_defs import (
    GLOBAL_SETTINGS_FIELDS,
    RENDER_FILAMENT_COLORS,
    RENDER_FILAMENT_NAMES,
    STATISTICS_FIELDS,
)
from core.output import (
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


# ── Shared field rendering (compare mode) ────────────────────

def _render_fields_compare(
    table: Table, fields, data_list: List[Dict], n: int, wiki_label: Callable,
) -> None:
    """Render a shared field list into a multi-column comparison table.

    Handles None separators, callable dynamic labels, and
    RENDER_FILAMENT_NAMES / RENDER_FILAMENT_COLORS sentinels.
    """
    for field in fields:
        if field is None:
            _add_separator(table, n)
            continue
        if field is RENDER_FILAMENT_NAMES:
            _render_compare_filament_names(table, data_list)
            continue
        if field is RENDER_FILAMENT_COLORS:
            _render_compare_filament_colors(table, data_list)
            continue
        label_or_fn, wiki_key, formatter, condition = field
        if condition and not any(condition(d) for d in data_list):
            continue
        if callable(label_or_fn):
            label = ""
            for d in data_list:
                label, wiki_key = label_or_fn(d)
                if label:
                    break
            if not label:
                continue
        else:
            label = label_or_fn
        display_label = wiki_label(label, wiki_key) if wiki_key else label
        _add_row(table, display_label, [formatter(d) for d in data_list])


def _print_compare_global_settings(
    console: Console, results: List[Dict], n: int, wiki_label: Callable,
) -> None:
    """Print Global Settings section with columns and diff highlighting."""
    profiles = [r['profile'] for r in results]
    table = _make_table(n)

    _render_fields_compare(table, GLOBAL_SETTINGS_FIELDS, profiles, n, wiki_label)

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
            styled.append(f"[{style}]\u2588\u2588[/{style}] {name}")
        return ', '.join(styled)
    name, style = _hex_to_color_name(str(colors))
    return f"[{style}]\u2588\u2588[/{style}] {name}"


def _render_compare_filament_names(table: Table, stats_list: List[Dict]) -> None:
    """Render filament name rows in compare mode (one row per extruder, N columns)."""
    if not any(s.get('filament_names') for s in stats_list):
        return
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


def _render_compare_filament_colors(table: Table, stats_list: List[Dict]) -> None:
    """Render filament colors row in compare mode."""
    if not any(s.get('filament_colors') for s in stats_list):
        return
    _add_row(table, "Filament Colors",
             [_format_stat_filament_colors(s) for s in stats_list])


def _print_compare_statistics(
    console: Console, results: List[Dict], n: int,
) -> None:
    """Print Statistics section for gcode comparison with columns."""
    stats_list = [r.get('statistics', {}) for r in results]
    if not any(stats_list):
        return

    table = _make_table(n)
    noop_label = lambda label, key: label
    _render_fields_compare(table, STATISTICS_FIELDS, stats_list, n, noop_label)

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
