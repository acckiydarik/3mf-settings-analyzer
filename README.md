# 3MF Settings Analyzer

A command-line tool that extracts and displays print settings from **3MF** and **Gcode** files in a structured, color-coded table format. Designed for quick inspection of slicer configurations without opening the slicer itself.

## Features

### 3MF analysis

- **Profile overview** -- printer, process profile, and filament presets at a glance
- **Global settings** -- layer height, walls, infill, speeds, temperatures, retraction, fan, and more
- **Per-object settings** -- individual overrides for each object on the build plate
- **Custom settings detection** -- highlights values that differ from the profile defaults with `*`
- **Part hierarchy** -- displays compound objects with their sub-components
- **Multi-plate support** -- handles projects with multiple build plates
- **Diff mode** -- side-by-side comparison of custom values against profile defaults

### Gcode analysis

- **Profile and global settings** -- same structured output as 3MF (extracted from CONFIG_BLOCK)
- **Custom global settings** -- detects profile overrides via `different_settings_to_system`
- **Object list** -- all printed objects extracted from gcode markers
- **Statistics panel** -- comprehensive print statistics:
  - Slicer info, file size, printer model, gcode flavor, nozzle type, bed type
  - Time estimates (total and first layer)
  - Layer info (count, height, max Z)
  - Filament usage (weight, volume, cost -- total and per extruder)
  - Filament details (name, vendor, type, color, density, diameter)
  - Temperature settings (nozzle and bed, including first layer)
  - Multi-material info (filament changes, prime tower status)

### Comparison mode

- **Side-by-side comparison** -- compare 2 to 4 files of the same type in a column-based layout
- **Auto-detection** -- comparison mode triggers automatically when multiple files are passed (no extra flags needed)
- **Diff highlighting** -- values that differ between files are highlighted with a muted background
- **Per-file columns** -- consistent column alignment across all sections (Profile, Global Settings, Custom Global, Objects, Statistics)
- **Missing value indicators** -- empty fields are shown as `--` with diff highlighting when other files have a value
- **Custom value footnote** -- 3MF comparison includes the `* = custom value` indicator for per-object overrides
- **Transposed objects layout** -- 3MF objects in comparison mode display each setting as a row with per-file value columns, including child objects and custom overrides
- **Zebra striping** -- objects tables use alternating row backgrounds for easier visual tracking across columns

### Common features

- **JSON export** -- raw structured data output for scripting and automation
- **Wiki links** -- clickable hyperlinks to [OrcaSlicer wiki](https://github.com/OrcaSlicer/OrcaSlicer/wiki) for each setting (`--wiki`). Reference data is auto-downloaded on first use (~1 MB) and cached locally for subsequent runs
- **Colored terminal output** -- powered by [Rich](https://github.com/Textualize/rich) with truecolor hex display
- **CSS3 color recognition** -- filament colors are identified by nearest match from the [W3C CSS3 Named Colors](https://www.w3.org/TR/css-color-3/#svg-color) standard (141 colors), with exact truecolor squares in the terminal

### Supported slicers

Works with 3MF and Gcode files produced by:

- [Bambu Studio](https://bambulab.com/en/download/studio)
- [OrcaSlicer](https://github.com/SoftFever/OrcaSlicer)
- [Snapmaker Orca](https://www.snapmaker.com/snapmaker-orca) (based on OrcaSlicer)
- Other slicers using the same 3MF metadata format or Gcode comment conventions

## Getting Started

### Prerequisites

- Python 3.9+

### Installation

```bash
git clone https://github.com/acckiydarik/3mf-settings-analyzer.git
cd 3mf-settings-analyzer
pip install .
```

This installs a `3mf-analyzer` command available from any directory.

For development, use editable mode (`pip install -e .`) so code changes take effect immediately.

> Without `pip install`, you can run directly via `python3 3mf_analyzer.py` from the project root.

### Quick start

```bash
3mf-analyzer model.3mf
3mf-analyzer model.gcode
```

## Usage

All examples below assume installation via `pip install .`.

```bash
3mf-analyzer <file> [file2 ...] [options]
```

### Options

| Flag | Description |
|------|-------------|
| `-h`, `--help` | Show help message and exit |
| `--version` | Show version number and exit |
| `--diff` | Show comparison of custom values against profile defaults |
| `--json` | Output JSON only (no formatted tables) |
| `-w`, `--wiki` | Add clickable wiki links to setting names (Cmd/Ctrl+click in terminal) |
| `--no-color` | Disable colored output (useful for file redirection) |
| `-v`, `--verbose` | Enable debug logging |
| `--update-wiki` | Update settings wiki data from OrcaSlicer GitHub |
| `--force-update-wiki` | Force re-download wiki data even if up to date |

### Examples

Analyze a 3MF file:

```bash
3mf-analyzer model.3mf
```

Analyze a Gcode file:

```bash
3mf-analyzer model.gcode
```

Show differences between custom and default values:

```bash
3mf-analyzer model.3mf --diff
```

Export structured data as JSON:

```bash
3mf-analyzer model.gcode --json
```

With clickable wiki links on setting names:

```bash
3mf-analyzer model.3mf --wiki
```

Save plain-text output to a file:

```bash
3mf-analyzer model.3mf --no-color > report.txt
```

Compare two Gcode files side by side:

```bash
3mf-analyzer file1.gcode file2.gcode
```

Compare up to four files (same type):

```bash
3mf-analyzer a.3mf b.3mf c.3mf d.3mf
```

Update wiki data from OrcaSlicer GitHub:

```bash
3mf-analyzer --update-wiki
```

## Output Overview

### 3MF output

```text
╭──────────────────────────────────────────────────────────────────────────────╮
│   3MF SETTINGS ANALYZER:                  example.3mf                        │
╰──────────────────────────────────────────────────────────────────────────────╯
─────────────────────────────────── PROFILE ────────────────────────────────────
╭──────────────────────────────────────────────────────────────────────────────╮
│   Printer       Bambu Lab A1 mini 0.4 nozzle                                 │
│   Process       0.20mm Standard @BBL A1M                                     │
│   Filament 1    Bambu PLA Basic @BBL A1M                                     │
╰──────────────────────────────────────────────────────────────────────────────╯
──────────────────────────────── GLOBAL SETTINGS ───────────────────────────────
╭──────────────────────────────────────────────────────────────────────────────╮
│   Layer Height                   0.2 mm                                      │
│   Wall Loops                     3                                           │
│   Sparse Infill Density          15%                                         │
│   ...                                                                        │
╰──────────────────────────────────────────────────────────────────────────────╯
──────────────── CUSTOM GLOBAL SETTINGS (changed from profile) ─────────────────
╭──────────────────────────────────────────────────────────────────────────────╮
│   * wall_loops               3                                               │
│   * seam_position            back                                            │
╰──────────────────────────────────────────────────────────────────────────────╯
─────────────────────────────────── OBJECTS ────────────────────────────────────
╭───────┬──────────────────────────┬──────────┬───────┬───────┬────────┬─────────┬──────┬───────╮
│ Plate │ Name                     │ Filament │ Layer │ Walls │ Infill │ Support │ Brim │ Speed │
├───────┼──────────────────────────┼──────────┼───────┼───────┼────────┼─────────┼──────┼───────┤
│   1   │ MyObject                 │    1     │  0.2  │   3   │   15   │   Off   │ Outer│  200  │
│   1   │ Assembly                 │    1     │  0.2  │   3   │  *80   │   *On   │ Outer│  200  │
│       │     ├─ enable_support: 1 │          │       │       │        │         │      │       │
│       │     └─ sparse_infill: 80 │          │       │       │        │         │      │       │
│       │   part_a                 │    1     │       │   3   │   80   │   On    │      │  200  │
│       │   part_b                 │    2     │       │   3   │   80   │   On    │      │  200  │
╰───────┴──────────────────────────┴──────────┴───────┴───────┴────────┴─────────┴──────┴───────╯
* = custom value (overrides profile default)
```

### Gcode output

```text
╭──────────────────────────────────────────────────────────────────────────────╮
│   GCODE SETTINGS ANALYZER:                model.gcode                        │
╰──────────────────────────────────────────────────────────────────────────────╯
─────────────────────────────────── PROFILE ────────────────────────────────────
╭──────────────────────────────────────────────────────────────────────────────╮
│   Printer       Snapmaker U1 (0.4 nozzle)                                    │
│   Process       0.16 High Quality @Snapmaker U1 (0.4 nozzle)                 │
│   Filament 1    Snapmaker PLA SnapSpeed @U1                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
──────────────────────────────── GLOBAL SETTINGS ───────────────────────────────
╭──────────────────────────────────────────────────────────────────────────────╮
│   Layer Height                   0.16 mm                                     │
│   Wall Loops                     2                                           │
│   ...                                                                        │
╰──────────────────────────────────────────────────────────────────────────────╯
─────────────────────────────────── OBJECTS ────────────────────────────────────
╭──────────────┬───────────────────────────────────────────────────────────────╮
│      #       │ Name                                                          │
├──────────────┼───────────────────────────────────────────────────────────────┤
│      1       │ STL Full Body (keychain).stl                                  │
╰──────────────┴───────────────────────────────────────────────────────────────╯
────────────────────────────────── STATISTICS ───────────────────────────────────
╭──────────────────────────────────────────────────────────────────────────────╮
│   Slicer                          Snapmaker Orca 2.2.1                       │
│   Generated                       2026-01-30 12:34:13                        │
│   File Size                       10.14 MB                                   │
│   Printer Model                   Snapmaker U1                               │
│                                                                              │
│   Estimated Time                  1h 11m 17s                                 │
│   Total Layers                    138                                        │
│                                                                              │
│   Filament Weight (Total)         11.26 g                                    │
│   Filament Weight Per Extruder    10.08 g, 0.87 g, 0.31 g                    │
│   Filament Volume Per Extruder    8.13 cm3, 0.70 cm3, 0.25 cm3               │
│   Filament Cost (Total)           $0.23                                      │
│   Filament Cost Per Extruder      $0.20, $0.02, $0.01                        │
│   Filament Changes                64                                         │
│   Filament 1                      Snapmaker PLA SnapSpeed @U1                │
│   Filament Colors                 ██ Gold, ██ White, ██ Black                │
│                                                                              │
│   First Layer Nozzle Temp         220 C                                      │
│   Bed Temp                        65 C                                       │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### Output sections

**PROFILE** -- printer name, process preset, filament list.

**GLOBAL SETTINGS** -- all key print parameters grouped by category:

| Category | Settings |
|----------|----------|
| Basic | Layer height, first layer height, line width, flow, wall loops, infill, top/bottom shells, brim, support, seam |
| Speeds | First layer, outer/inner wall, infill, top surface, travel, bridge |
| Patterns | Infill pattern, top surface pattern, print sequence, spiral/vase mode, ironing, fuzzy skin |
| Retraction | Length, speed, Z-hop, pressure advance |
| Cooling | Fan min/max, layer cooling slowdown |
| Temperature | Nozzle, bed |
| Features | Arc fitting, overhang speed, timelapse |

**CUSTOM GLOBAL SETTINGS** -- parameters changed from the profile defaults.

**OBJECTS** (3MF) -- a table with per-object settings:

| Column | Description |
|--------|-------------|
| Plate | Build plate number |
| Name | Object or part name (parts are indented) |
| Filament | Filament number (1, 2, 3...) |
| Layer | Layer height in mm |
| Walls | Number of wall loops |
| Infill | Infill density percentage |
| Support | Support enabled (On/Off) |
| Brim | Brim type |
| Speed | Outer wall speed in mm/s |

Custom values are marked with `*`. Per-object overrides are displayed in a tree below each object.

**OBJECTS** (Gcode) -- a numbered list of object names. Gcode does not contain per-object settings.

**STATISTICS** (Gcode only) -- print statistics including slicer info, time estimates, layer details, filament usage (weight/volume/cost per extruder), filament properties, and temperatures.

### Diff mode

With `--diff`, custom values show the original default alongside:

```text
│  *80 <-15%  │  *On <-Off  │
```

### Comparison output

When 2-4 files of the same type are passed, the tool automatically switches to comparison mode with a column-based layout:

```text
╭──────────────────────────────────────────────────────────────────────────────╮
│   GCODE SETTINGS COMPARISON:      file_a.gcode         file_b.gcode         │
╰──────────────────────────────────────────────────────────────────────────────╯
──────────────────────────────────── PROFILE ───────────────────────────────────
╭──────────────────────────────────────────────────────────────────────────────╮
│   Printer                          Bambu Lab A1M         Bambu Lab A1M      │
│   Process                          0.20mm Standard       0.16mm Quality     │
│   Filament 1                       Bambu PLA Basic       Bambu PLA Basic    │
╰──────────────────────────────────────────────────────────────────────────────╯
─────────────────────────────── GLOBAL SETTINGS ───────────────────────────────
╭──────────────────────────────────────────────────────────────────────────────╮
│   Layer Height                     0.2 mm                0.16 mm            │
│   Wall Loops                       3                     2                  │
│   ...                                                                       │
╰──────────────────────────────────────────────────────────────────────────────╯
```

Values that differ between files are highlighted with a muted background. Empty fields are shown as `--`.

For 3MF files, the Objects section uses a transposed layout where each object's settings are displayed as rows with per-file value columns:

```text
─────────────────────────────────── OBJECTS ────────────────────────────────────
╭──────────────────────────────────┬──────────────────────┬──────────────────────╮
│ Setting                          │ Value                │ Value                │
├──────────────────────────────────┼──────────────────────┼──────────────────────┤
│ #1  MyObject.stp                 │                      │                      │
│   Plate                          │ 1                    │ 1                    │
│   Filament                       │ 1                    │ 2                    │
│   Infill Density                 │ 15                   │ 80                   │
│   Support                        │ Off                  │ On                   │
│   └─ * sparse_infill_density     │ --                   │ 80%                  │
├──────────────────────────────────┼──────────────────────┼──────────────────────┤
│ #2  AnotherObject.stp            │                      │                      │
│   ...                            │                      │                      │
╰──────────────────────────────────┴──────────────────────┴──────────────────────╯
* = custom value (overrides profile default)
```

Objects tables in both single-file and comparison modes use alternating row backgrounds (zebra striping) for easier row tracking across columns.

## How It Works

### 3MF files

A `.3mf` file is a ZIP archive with the following structure relevant to this tool:

```text
file.3mf
├── Metadata/
│   ├── project_settings.config   <- global print settings (JSON)
│   └── model_settings.config     <- per-object settings (XML)
├── Plate_1/
│   └── *.stl / *.model
└── ...
```

The analyzer reads `project_settings.config` for global/profile settings and `model_settings.config` for per-object and per-part overrides.

### Gcode files

Gcode files are plain-text machine instruction files. OrcaSlicer-compatible slicers embed metadata as comments with a defined block structure:

```text
; HEADER_BLOCK_START          <- slicer info, layer count, max height
; HEADER_BLOCK_END

; printing object NAME id:XX  <- object markers (throughout file)
; stop printing object NAME

; filament used [g] = ...     <- statistics (before CONFIG_BLOCK)
; total filament cost = ...
; estimated printing time = ...

; CONFIG_BLOCK_START          <- all slicer settings (key = value)
; CONFIG_BLOCK_END
```

The analyzer parses:
1. **Header** (first 100 lines) for slicer version and basic info
2. **Object markers** (full file scan) for printed object names
3. **Statistics** (last 100KB) for filament usage, time, and layer counts
4. **CONFIG_BLOCK** (last 100KB) for all slicer settings

## Project Structure

```text
3mf-settings-analyzer/
├── 3mf_analyzer.py             # Thin entry point (calls core.cli.main)
├── pyproject.toml              # Package metadata, dependencies, CLI entry point
├── requirements.txt            # Python dependencies
├── requirements-dev.txt        # Dev dependencies (pytest, coverage)
├── core/                       # Core package
│   ├── __init__.py                 # Public API exports
│   ├── _version.py                 # Single source of truth for __version__
│   ├── constants.py                # Shared constants (SYSTEM_KEYS, BOOL_TRUE, etc.)
│   ├── field_defs.py               # Shared field definitions for output + compare
│   ├── threemf.py                  # ThreeMFAnalyzer class + _is_custom helper
│   ├── gcode.py                    # GcodeAnalyzer class
│   ├── output.py                   # Rich formatting: panels, tables, colors, helpers
│   ├── compare.py                  # Side-by-side comparison for 2-4 files with diff highlighting
│   ├── cli.py                      # argparse, main(), multi-file routing, setup_logging()
│   ├── settings_wiki.py            # OrcaSlicer settings reference module
│   └── data/                       # Package data (included in pip install)
│       ├── css3_colors.json            # W3C CSS3 named colors for color recognition
│       └── settings_wiki.json          # Cached settings metadata (auto-generated via --update-wiki)
├── tests/                      # Unit tests
│   ├── __init__.py
│   ├── conftest.py                 # Pytest fixtures (3MF + Gcode)
│   ├── test_constants.py           # Tests for core.constants
│   ├── test_threemf.py             # Tests for core.threemf
│   ├── test_gcode.py               # Tests for core.gcode
│   ├── test_output.py              # Tests for core.output
│   ├── test_cli.py                 # Tests for core.cli
│   ├── test_compare.py             # Tests for core.compare (comparison mode)
│   └── test_settings_wiki.py       # Tests for settings_wiki
├── README.md                   # Documentation
├── LICENSE                     # MIT license
├── .gitignore                  # Git ignore rules
└── .gitattributes              # GitHub linguist overrides
```

## Requirements

- Python 3.9+
- [rich](https://github.com/Textualize/rich) >= 13.0.0
- [defusedxml](https://github.com/tiran/defusedxml) >= 0.7.1 (**required** for XML security)

## Contributing

Contributions are welcome. If you found a bug or have a feature request, please [open an issue](https://github.com/acckiydarik/3mf-settings-analyzer/issues). Pull requests are also appreciated.

## Development

### Running Tests

Install in editable mode with dev dependencies and run the test suite:

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT

Wiki reference data is extracted from [OrcaSlicer](https://github.com/OrcaSlicer/OrcaSlicer) (AGPL-3.0). The source files are not included in this repository and are downloaded on demand.
