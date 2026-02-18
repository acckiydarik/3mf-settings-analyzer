"""Command-line interface for the 3MF Settings Analyzer."""

import argparse
import json
import logging
import sys
import zipfile
from pathlib import Path
from xml.etree.ElementTree import ParseError

from rich.console import Console

from core import __version__
from core.constants import FILE_EXTENSION_3MF, FILE_EXTENSION_GCODE
from core.gcode import GcodeAnalyzer
from core.output import print_gcode_results, print_results
from core.threemf import ThreeMFAnalyzer

logger = logging.getLogger(__name__)


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
        description='3MF Settings Analyzer - Analyze 3MF and Gcode files and display slicer settings',
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

    # Pre-load wiki data before output so download messages don't interrupt tables
    if args.wiki and not args.json:
        try:
            from settings_wiki import _load_cache, _JSON_PATH
            if not _JSON_PATH.exists():
                console = Console(no_color=args.no_color)
                console.print("[cyan]Downloading wiki data from OrcaSlicer GitHub...[/cyan]")
                _load_cache()
                if _JSON_PATH.exists():
                    console.print("[green]Wiki data downloaded successfully.[/green]")
                else:
                    console.print("[yellow]Wiki data unavailable. Wiki links will be disabled.[/yellow]")
            else:
                _load_cache()
        except Exception as e:
            logger.debug("Wiki pre-load failed: %s", e)

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
    except ParseError as e:
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
