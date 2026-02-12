# 3MF Settings Analyzer

A command-line tool that extracts and displays print settings from 3MF files in a structured, color-coded table format. Designed for quick inspection of slicer configurations without opening the slicer itself.

## Features

- **Profile overview** -- printer, process profile, and filament presets at a glance
- **Global settings** -- layer height, walls, infill, speeds, temperatures, retraction, fan, and more
- **Per-object settings** -- individual overrides for each object on the build plate
- **Custom settings detection** -- highlights values that differ from the profile defaults with `*`
- **Part hierarchy** -- displays compound objects with their sub-components
- **Multi-plate support** -- handles projects with multiple build plates
- **Diff mode** -- side-by-side comparison of custom values against profile defaults
- **JSON export** -- raw structured data output for scripting and automation
- **Wiki links** -- clickable hyperlinks to [OrcaSlicer wiki](https://github.com/OrcaSlicer/OrcaSlicer/wiki) for each setting (`--wiki`)
- **Colored terminal output** -- powered by [Rich](https://github.com/Textualize/rich)

### Supported slicers

Works with 3MF files produced by:

- [Bambu Studio](https://bambulab.com/en/download/studio)
- [OrcaSlicer](https://github.com/SoftFever/OrcaSlicer)
- [Snapmaker Orca](https://www.snapmaker.com/snapmaker-orca) (based on OrcaSlicer)
- Other slicers using the same 3MF metadata format (project_settings.config / model_settings.config)

## Getting Started

### Prerequisites

- Python 3.6+

### Installation

```bash
git clone https://github.com/acckiydarik/3mf-settings-analyzer.git
cd 3mf-settings-analyzer
pip install -r requirements.txt
```

### Quick start

```bash
python3 analyze.py model.3mf
```

## Usage

```bash
python3 analyze.py <file.3mf> [options]
```

### Options

| Flag | Description |
|------|-------------|
| `-h`, `--help` | Show help message and exit |
| `--version` | Show version number and exit |
| `--diff` | Show comparison of custom values against profile defaults |
| `--json` | Output raw JSON data |
| `-w`, `--wiki` | Add clickable wiki links to setting names (Cmd/Ctrl+click in terminal) |
| `--no-color` | Disable colored output (useful for file redirection) |
| `-v`, `--verbose` | Enable debug logging |
| `--update-wiki` | Update settings wiki data from OrcaSlicer GitHub |
| `--force-update-wiki` | Force re-download wiki data even if up to date |

### Examples

Analyze a file with default output:

```bash
python3 analyze.py model.3mf
```

Show differences between custom and default values:

```bash
python3 analyze.py model.3mf --diff
```

Export structured data as JSON:

```bash
python3 analyze.py model.3mf --json
```

With clickable wiki links on setting names:

```bash
python3 analyze.py model.3mf --wiki
```

Save plain-text output to a file:

```bash
python3 analyze.py model.3mf --no-color > report.txt
```

Update wiki data from OrcaSlicer GitHub:

```bash
python3 analyze.py --update-wiki
```

## Output Overview

The analyzer produces several sections. Here is a full example:

```
╭──────────────────────────────────────────────────────────────────────────────╮
│ 3MF SETTINGS ANALYZER  │  example.3mf                                        │
╰──────────────────────────────────────────────────────────────────────────────╯

PROFILE
  Printer       Bambu Lab A1 mini 0.4 nozzle
  Process       0.20mm Standard @BBL A1M
  Filament 1    Bambu PLA Basic @BBL A1M

GLOBAL SETTINGS
  Layer Height          0.2 mm
  First Layer Height    0.2 mm
  Line Width            0.42 mm
  Wall Loops            2
  Infill                15%
  Top/Bottom            5/3 layers
  Brim                  no_brim
  Support               Off
  Seam                  aligned

  Outer Wall     200 mm/s
  Inner Wall     300 mm/s
  Travel         700 mm/s
  Bridge         50 mm/s

  Infill Pattern    gyroid
  Top Surface       monotonicline
  Print Sequence    by layer

  Retraction       0.8 mm
  Z-Hop            0.4 mm
  Pressure Adv     0.02
  Fan Min/Max      60% / 80%
  Slowdown         On (6s)

  Nozzle Temp    220°C
  Bed Temp       60°C
  Features:  Arc Fitting, Overhang Slowdown

CUSTOM GLOBAL SETTINGS (changed from profile)
  * seam_position: back
  * wall_loops: 3
  * sparse_infill_pattern: gyroid

OBJECTS
╭───────┬──────────────────────────┬──────────┬───────┬───────┬────────┬─────────┬──────┬───────╮
│ Plate │ Name                     │ Filament │ Layer │ Walls │ Infill │ Support │ Brim │ Speed │
├───────┼──────────────────────────┼──────────┼───────┼───────┼────────┼─────────┼──────┼───────┤
│   1   │ MyObject                 │    1     │  0.2  │   2   │   15   │   Off   │  No  │  200  │
├───────┼──────────────────────────┼──────────┼───────┼───────┼────────┼─────────┼──────┼───────┤
│   1   │ Assembly                 │    1     │  0.2  │   2   │  *80   │   *On   │  No  │  200  │
│       │     ├─ enable_support: 1 │          │       │       │        │         │      │       │
│       │     └─ sparse_infill: 80 │          │       │       │        │         │      │       │
│       │   part_a                 │    1     │       │   2   │   80   │   On    │      │  200  │
│       │   part_b                 │    2     │       │   2   │   80   │   On    │      │  200  │
╰───────┴──────────────────────────┴──────────┴───────┴───────┴────────┴─────────┴──────┴───────╯

* = custom value (overrides profile default)
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

**OBJECTS** -- a table with per-object settings:

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

Custom values are marked with `*`. Per-object overrides (ironing, infill density, support, etc.) are displayed in a tree below each object.

### Diff mode

With `--diff`, custom values show the original default alongside:

```
│  *80 <-15%  │  *On <-Off  │
```

## How 3MF Files Work

A `.3mf` file is a ZIP archive with the following structure relevant to this tool:

```
file.3mf
├── Metadata/
│   ├── project_settings.config   <- global print settings (JSON)
│   └── model_settings.config     <- per-object settings (XML)
├── Plate_1/
│   └── *.stl / *.model
└── ...
```

The analyzer reads `project_settings.config` for global/profile settings and `model_settings.config` for per-object and per-part overrides.

## Project Structure

```
3mf-settings-analyzer/
├── analyze.py          # Main CLI script
├── settings_wiki.py    # OrcaSlicer settings reference module
├── data/
│   ├── PrintConfig.cpp     # OrcaSlicer source (setting definitions)
│   ├── Tab.cpp             # OrcaSlicer source (wiki page mappings)
│   └── settings_wiki.json  # Cached parsed settings metadata
├── requirements.txt    # Python dependencies
├── README.md           # Documentation
├── LICENSE             # MIT license
└── .gitignore          # Git ignore rules
```

## Requirements

- Python 3.6+
- [rich](https://github.com/Textualize/rich) >= 13.0.0

## Contributing

Contributions are welcome. If you found a bug or have a feature request, please [open an issue](https://github.com/acckiydarik/3mf-settings-analyzer/issues). Pull requests are also appreciated.

## License

MIT
