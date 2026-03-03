"""Command-line interface for the 3MF Settings Analyzer."""

import argparse
import json
import logging
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List
from xml.etree.ElementTree import ParseError

from rich.console import Console

from core._version import __version__
from core.constants import FILE_EXTENSION_3MF, FILE_EXTENSION_GCODE, MAX_COMPARE_FILES
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


def _preload_wiki(args) -> None:
    """Pre-load wiki data before output so download messages don't interrupt tables."""
    if not args.wiki or args.json:
        return
    try:
        from core.settings_wiki import _load_cache, _JSON_PATH
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


def _analyze_file(filepath: Path, file_type: str) -> Dict[str, Any]:
    """Parse a single file and return the result dict.

    Raises:
        zipfile.BadZipFile, json.JSONDecodeError, ParseError, ValueError, OSError
    """
    if file_type == '3mf':
        analyzer = ThreeMFAnalyzer(filepath)
        return analyzer.analyze()
    else:
        analyzer = GcodeAnalyzer(filepath)
        return analyzer.analyze()


def _parse_multiple_files(filepaths: List[Path], file_type: str) -> List[Dict[str, Any]]:
    """Parse multiple files, logging errors for failures.

    Returns list of successfully parsed results. Failed files are skipped
    with a logged error.
    """
    results: List[Dict[str, Any]] = []
    for fp in filepaths:
        try:
            results.append(_analyze_file(fp, file_type))
        except zipfile.BadZipFile:
            logger.error("Invalid or corrupted ZIP/3MF file (skipped): %s", fp)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse project settings in %s (skipped): %s", fp, e)
        except ParseError as e:
            logger.error("Failed to parse model settings in %s (skipped): %s", fp, e)
        except ValueError as e:
            logger.error("Validation error in %s (skipped): %s", fp, e)
        except OSError as e:
            logger.error("File system error for %s (skipped): %s", fp, e)
    return results


def _run_single(filepath: Path, file_type: str, args) -> None:
    """Run single-file analysis (existing behavior)."""
    try:
        result = _analyze_file(filepath, file_type)

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif file_type == '3mf':
            print_results(result, show_diff=args.diff, no_color=args.no_color, wiki=args.wiki)
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
        logger.error("Security or validation error: %s", e)
        sys.exit(1)
    except OSError as e:
        logger.error("File system error: %s", e)
        sys.exit(1)


def _run_comparison(filepaths: List[Path], file_type: str, args) -> None:
    """Run multi-file comparison mode."""
    from core.compare import print_3mf_comparison, print_gcode_comparison

    results = _parse_multiple_files(filepaths, file_type)

    if not results:
        logger.error("No files were parsed successfully")
        sys.exit(1)

    if len(results) == 1:
        logger.warning("Only one file parsed successfully, falling back to single-file mode")
        if args.json:
            print(json.dumps(results[0], indent=2, ensure_ascii=False))
        elif file_type == '3mf':
            print_results(results[0], show_diff=args.diff, no_color=args.no_color, wiki=args.wiki)
        else:
            print_gcode_results(results[0], show_diff=args.diff, no_color=args.no_color, wiki=args.wiki)
        return

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    if file_type == '3mf':
        print_3mf_comparison(results, show_diff=args.diff, no_color=args.no_color, wiki=args.wiki)
    else:
        print_gcode_comparison(results, no_color=args.no_color, wiki=args.wiki)


def main():
    parser = argparse.ArgumentParser(
        description='3MF Settings Analyzer - Analyze 3MF and Gcode files and display slicer settings',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  3mf-analyzer model.3mf
  3mf-analyzer model.gcode
  3mf-analyzer model.3mf --diff
  3mf-analyzer model.3mf --json
  3mf-analyzer model.3mf --verbose
  3mf-analyzer model.3mf --wiki
  3mf-analyzer model.3mf --no-color > output.txt
  3mf-analyzer file1.gcode file2.gcode
  3mf-analyzer a.gcode b.gcode c.gcode d.gcode
  3mf-analyzer --update-wiki
"""
    )
    parser.add_argument('files', nargs='*', help='Path to 3MF or Gcode file(s). Pass 2-4 files for comparison mode.')
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
        from core.settings_wiki import update as wiki_update
        console = Console(no_color=args.no_color)
        console.print("[cyan]Updating wiki data from OrcaSlicer GitHub...[/cyan]")
        wiki_ok = True
        try:
            updated = wiki_update(force=args.force_update_wiki)
            if updated:
                console.print("[green]Wiki data updated successfully.[/green]")
            else:
                console.print("[yellow]Wiki data is already up to date.[/yellow]")
        except Exception as e:
            logger.error("Failed to update wiki data: %s", e)
            console.print(f"[red]Failed to update wiki data: {e}[/red]")
            wiki_ok = False
        if not args.files:
            sys.exit(0 if wiki_ok else 1)

    if not args.files:
        parser.error("the following arguments are required: files")

    if len(args.files) > MAX_COMPARE_FILES:
        logger.error("Maximum %d files for comparison (got %d)", MAX_COMPARE_FILES, len(args.files))
        sys.exit(1)

    # Validate all files exist and detect types
    filepaths: List[Path] = []
    file_types: List[str] = []
    for raw_path in args.files:
        fp = Path(raw_path)
        if not fp.exists():
            logger.error("File not found: %s", fp)
            sys.exit(1)
        ft = _get_file_type(fp)
        if ft == 'unknown':
            logger.error("Unsupported file type: %s (use .3mf or .gcode)", fp.suffix)
            sys.exit(1)
        filepaths.append(fp)
        file_types.append(ft)

    # Validate all files are the same type
    unique_types = set(file_types)
    if len(unique_types) > 1:
        logger.error("Cannot compare .gcode with .3mf files. All files must be the same type.")
        sys.exit(1)

    file_type = file_types[0]

    _preload_wiki(args)

    try:
        if len(filepaths) == 1:
            _run_single(filepaths[0], file_type, args)
        else:
            _run_comparison(filepaths, file_type, args)
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(130)
