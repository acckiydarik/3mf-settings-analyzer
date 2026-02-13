#!/usr/bin/env python3
"""
OrcaSlicer Settings Reference Module.

Parses OrcaSlicer source files (PrintConfig.cpp, Tab.cpp) to build a settings
reference with labels, descriptions, units, categories, and wiki page links.

Usage:
    As a module:
        from settings_wiki import get_wiki_url, get_setting_info

    Update data from GitHub:
        python settings_wiki.py
"""

import hashlib
import json
import logging
import os
import re
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════

# Wiki base URL - can be overridden via environment variable
WIKI_BASE = os.environ.get(
    "ORCASLICER_WIKI_BASE",
    "https://github.com/OrcaSlicer/OrcaSlicer/wiki/"
)

# GitHub repository settings - can be overridden for forks or local development
_GITHUB_REPO_OWNER = os.environ.get("ORCASLICER_REPO_OWNER", "OrcaSlicer")
_GITHUB_REPO_NAME = os.environ.get("ORCASLICER_REPO_NAME", "OrcaSlicer")
_GITHUB_BRANCH = os.environ.get("ORCASLICER_BRANCH", "main")

_GITHUB_API_BASE = f"https://api.github.com/repos/{_GITHUB_REPO_OWNER}/{_GITHUB_REPO_NAME}/contents/src"
_GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{_GITHUB_REPO_OWNER}/{_GITHUB_REPO_NAME}/{_GITHUB_BRANCH}/src"

# Network timeout settings (in seconds)
_API_TIMEOUT = int(os.environ.get("ORCASLICER_API_TIMEOUT", "10"))
_DOWNLOAD_TIMEOUT = int(os.environ.get("ORCASLICER_DOWNLOAD_TIMEOUT", "30"))

# SHA hash length for change detection
_SHA_HASH_LENGTH = 12

_SOURCES = {
    "Tab.cpp": {
        "api_url": f"{_GITHUB_API_BASE}/slic3r/GUI/Tab.cpp",
        "raw_url": f"{_GITHUB_RAW_BASE}/slic3r/GUI/Tab.cpp",
    },
    "PrintConfig.cpp": {
        "api_url": f"{_GITHUB_API_BASE}/libslic3r/PrintConfig.cpp",
        "raw_url": f"{_GITHUB_RAW_BASE}/libslic3r/PrintConfig.cpp",
    },
}

def _get_data_dir() -> Path:
    """Get data directory, supporting PyInstaller frozen executables."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running as PyInstaller bundle
        return Path(sys._MEIPASS) / "data"
    return Path(__file__).parent / "data"

_DATA_DIR = _get_data_dir()
_JSON_PATH = _DATA_DIR / "settings_wiki.json"

# Manual fallback wiki page mappings for settings that can't be automatically
# extracted from Tab.cpp (no label_path or append_single_option_line pattern).
# These are kept minimal -- only for settings that appear in our output.
_WIKI_FALLBACKS = {
    "bridge_speed": "speed_settings_other_layers_speed#bridge",
    "internal_bridge_speed": "speed_settings_other_layers_speed#bridge",
    "bed_temperature": "material_temperatures#bed",
    # top_one_wall_type is deprecated, maps to same page as only_one_wall_top
    "top_one_wall_type": "quality_settings_wall_and_surfaces#only-one-wall",
}

# C++ type to human-readable type mapping
_TYPE_MAP = {
    "coFloat": "float",
    "coFloats": "float",
    "coInt": "int",
    "coInts": "int",
    "coBool": "bool",
    "coBools": "bool",
    "coPercent": "percent",
    "coPercents": "percent",
    "coString": "string",
    "coStrings": "string",
    "coEnum": "enum",
    "coPoint": "point",
    "coPoints": "points",
}


# ═══════════════════════════════════════════════════════════════
# Parsing
# ═══════════════════════════════════════════════════════════════

def _parse_print_config(text: str) -> dict:
    """Parse PrintConfig.cpp to extract setting metadata.

    Extracts blocks starting with this->add("key", coType) followed by
    def->field = value lines.

    Returns:
        Dict mapping setting_key -> {label, category, tooltip, sidetext, type, default}
    """
    settings = {}

    # Split into blocks: each starts with this->add(
    # Pattern: def = this->add("key", coType);
    add_pattern = re.compile(
        r'this->add\("(\w+)",\s*(co\w+)\)'
    )

    # Field patterns
    label_pattern = re.compile(r'def->label\s*=\s*L\("(.+?)"\)')
    full_label_pattern = re.compile(r'def->full_label\s*=\s*L\("(.+?)"\)')
    category_pattern = re.compile(r'def->category\s*=\s*L\("(.+?)"\)')
    sidetext_pattern = re.compile(r'def->sidetext\s*=\s*L\("(.+?)"\)')

    # Tooltip can span multiple lines with string concatenation
    # First capture single-line tooltips, then handle multi-line
    tooltip_single_pattern = re.compile(
        r'def->tooltip\s*=\s*L\("(.+?)"\);', re.DOTALL
    )

    # Default value patterns
    default_patterns = [
        re.compile(r'set_default_value\(new\s+ConfigOption(?:Float|Int|Percent)\(([^)]+)\)'),
        re.compile(r'set_default_value\(new\s+ConfigOptionBool\((\w+)\)'),
    ]

    # Split text into setting blocks
    lines = text.split('\n')
    current_key = None
    current_type = None
    current_block_lines = []

    def _process_block(key, ctype, block_text):
        """Process a single setting block."""
        if not key:
            return

        entry = {"type": _TYPE_MAP.get(ctype, ctype)}

        # Label
        m = label_pattern.search(block_text)
        if m:
            entry["label"] = m.group(1)

        # Full label (overrides label for display)
        m = full_label_pattern.search(block_text)
        if m:
            entry["full_label"] = m.group(1)

        # Category
        m = category_pattern.search(block_text)
        if m:
            entry["category"] = m.group(1)

        # Sidetext (unit)
        m = sidetext_pattern.search(block_text)
        if m:
            entry["sidetext"] = m.group(1)

        # Tooltip - handle multi-line string concatenation
        tooltip_start = re.search(r'def->tooltip\s*=\s*L\(', block_text)
        if tooltip_start:
            # Extract everything from L( to the closing );
            rest = block_text[tooltip_start.end():]
            # Collect all quoted strings until );
            tooltip_parts = re.findall(r'"((?:[^"\\]|\\.)*)"', rest.split(');')[0])
            if tooltip_parts:
                tooltip = ''.join(tooltip_parts)
                # Clean up escape sequences
                tooltip = tooltip.replace('\\n', '\n').replace('\\"', '"')
                entry["tooltip"] = tooltip

        # Default value
        for pat in default_patterns:
            m = pat.search(block_text)
            if m:
                val = m.group(1).strip()
                # Clean up common patterns
                if val in ('true', 'false'):
                    entry["default"] = val
                else:
                    # Try to simplify numeric values
                    try:
                        if '.' in val:
                            entry["default"] = str(float(val))
                        else:
                            entry["default"] = str(int(val))
                    except (ValueError, TypeError):
                        entry["default"] = val
                break

        # Only store if we have at least a label
        if "label" in entry:
            settings[key] = entry

    for line in lines:
        m = add_pattern.search(line)
        if m:
            # Process previous block
            if current_key:
                _process_block(current_key, current_type, '\n'.join(current_block_lines))

            current_key = m.group(1)
            current_type = m.group(2)
            current_block_lines = [line]
        elif current_key:
            current_block_lines.append(line)

    # Process last block
    if current_key:
        _process_block(current_key, current_type, '\n'.join(current_block_lines))

    return settings


def _parse_tab_cpp(text: str) -> dict:
    """Parse Tab.cpp to extract setting_key -> wiki_page mapping.

    Two extraction strategies:
    1. append_single_option_line("key", "wiki_page") -- direct mapping
    2. label_path = "wiki_page" followed by get_option("key") -- group mapping
       (used for settings grouped in a single line, e.g. bridge_speed, fan speeds, temps)

    Returns:
        Dict mapping setting_key -> wiki_page string
    """
    wiki_map = {}

    # Strategy 1: Direct append_single_option_line calls
    # Matches both 2-arg and 3-arg forms
    direct_pattern = re.compile(
        r'append_single_option_line\("(\w+)"\s*,\s*"([^"]+)"'
    )
    for m in direct_pattern.finditer(text):
        key = m.group(1)
        wiki_page = m.group(2)
        if key not in wiki_map:
            wiki_map[key] = wiki_page

    # Strategy 2: label_path blocks with get_option
    # Pattern: line.label_path = "wiki_page"; ... line.append_option(optgroup->get_option("key")); ... optgroup->append_line(line);
    # We scan line by line, tracking current label_path context
    lines = text.split('\n')
    current_label_path = None
    for line in lines:
        # Check for label_path assignment
        lp_match = re.search(r'label_path\s*=\s*"([^"]+)"', line)
        if lp_match:
            current_label_path = lp_match.group(1)
            continue

        # Check for get_option within current label_path context
        if current_label_path:
            opt_match = re.search(r'get_option\("(\w+)"', line)
            if opt_match:
                key = opt_match.group(1)
                # Only add if not already mapped (direct mapping takes priority)
                if key not in wiki_map:
                    wiki_map[key] = current_label_path
                continue

            # Reset label_path on append_line (end of group)
            if 'append_line' in line:
                current_label_path = None

    return wiki_map


def _build_settings_data() -> dict:
    """Parse both .cpp files and merge into a single settings dict.

    Returns:
        Complete settings data dict with _meta and settings.
    """
    tab_path = _DATA_DIR / "Tab.cpp"
    config_path = _DATA_DIR / "PrintConfig.cpp"

    if not tab_path.exists():
        logger.error("Tab.cpp not found in %s. Run 'python settings_wiki.py' to download.", _DATA_DIR)
        return {"_meta": {}, "settings": {}}

    if not config_path.exists():
        logger.error("PrintConfig.cpp not found in %s. Run 'python settings_wiki.py' to download.", _DATA_DIR)
        return {"_meta": {}, "settings": {}}

    # Read source files
    tab_text = tab_path.read_text(encoding='utf-8')
    config_text = config_path.read_text(encoding='utf-8')

    # Parse
    settings = _parse_print_config(config_text)
    wiki_map = _parse_tab_cpp(tab_text)

    # Merge wiki pages into settings
    for key, wiki_page in wiki_map.items():
        if key in settings:
            settings[key]["wiki_page"] = wiki_page
        else:
            # Setting exists in Tab.cpp but not in PrintConfig.cpp
            settings[key] = {"wiki_page": wiki_page}

    # Apply manual fallback mappings for settings not captured by parsers
    for key, wiki_page in _WIKI_FALLBACKS.items():
        if key in settings and "wiki_page" not in settings[key]:
            settings[key]["wiki_page"] = wiki_page
        elif key not in settings:
            settings[key] = {"wiki_page": wiki_page}

    # Compute file SHAs for change detection
    tab_sha = hashlib.sha256(tab_text.encode()).hexdigest()[:_SHA_HASH_LENGTH]
    config_sha = hashlib.sha256(config_text.encode()).hexdigest()[:_SHA_HASH_LENGTH]

    return {
        "_meta": {
            "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "wiki_base": WIKI_BASE,
            "sha": {
                "Tab.cpp": tab_sha,
                "PrintConfig.cpp": config_sha,
            },
            "total_settings": len(settings),
            "with_wiki_page": sum(1 for s in settings.values() if "wiki_page" in s),
        },
        "settings": dict(sorted(settings.items())),
    }


def generate_json() -> Path:
    """Parse .cpp files and write settings_wiki.json.

    Returns:
        Path to the generated JSON file.
    """
    data = _build_settings_data()

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    meta = data["_meta"]
    logger.debug(
        "Generated %s: %d settings (%d with wiki links)",
        _JSON_PATH.name,
        meta.get("total_settings", 0),
        meta.get("with_wiki_page", 0),
    )
    return _JSON_PATH


# ═══════════════════════════════════════════════════════════════
# Update from GitHub
# ═══════════════════════════════════════════════════════════════

def _get_github_sha(api_url: str) -> Optional[str]:
    """Get file SHA from GitHub API without downloading content."""
    try:
        req = urllib.request.Request(api_url, headers={"Accept": "application/vnd.github.v3+json"})
        with urllib.request.urlopen(req, timeout=_API_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
            return data.get("sha")
    except (urllib.error.URLError, json.JSONDecodeError, KeyError) as e:
        logger.warning("Failed to get SHA from GitHub: %s", e)
        return None


def _download_file(raw_url: str, dest: Path) -> bool:
    """Download a file from GitHub raw URL with atomic write.
    
    Uses a temporary file and rename to ensure atomic writes,
    preventing partial/corrupted files on errors.
    
    Args:
        raw_url: URL to download from.
        dest: Destination path to save the file.
        
    Returns:
        True if download succeeded, False otherwise.
    """
    import tempfile
    
    # Security: only allow HTTPS downloads
    if not raw_url.startswith('https://'):
        logger.error("Refusing to download from non-HTTPS URL: %s", raw_url)
        return False
    
    try:
        req = urllib.request.Request(raw_url)
        with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT) as resp:
            content = resp.read()
        
        # Validate content is not HTML error page (GitHub returns HTML on errors)
        if content.startswith(b'<!DOCTYPE') or content.startswith(b'<html'):
            logger.error("Downloaded HTML instead of expected file from %s", raw_url)
            return False
        
        # Atomic write: write to temp file then rename
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode='wb', dir=dest.parent, delete=False, suffix='.tmp'
        ) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        
        # Atomic rename (on POSIX) / replace on Windows
        tmp_path.replace(dest)
        return True
    except urllib.error.URLError as e:
        logger.error("Failed to download %s: %s", raw_url, e)
        return False
    except OSError as e:
        logger.error("Failed to write file %s: %s", dest, e)
        # Cleanup temp file if it exists
        if 'tmp_path' in locals() and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        return False


def update(force: bool = False) -> bool:
    """Check for updates and re-download .cpp files if changed.

    Uses SHA256 content hashing to detect changes. Downloads remote files
    and compares their hash against locally stored hashes.

    Args:
        force: If True, skip hash check and always re-download.

    Returns:
        True if files were updated, False if already up to date or error.
    """
    if force:
        # Force mode: skip all checks, download everything
        return _download_all_and_regenerate()

    # Load existing content hashes for comparison
    stored_hashes = {}
    if _JSON_PATH.exists():
        try:
            with open(_JSON_PATH, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                stored_hashes = existing_data.get("_meta", {}).get("sha", {})
        except (json.JSONDecodeError, KeyError):
            pass

    # Check if local files exist
    for filename in _SOURCES:
        if not (_DATA_DIR / filename).exists():
            logger.debug("Local file %s missing, downloading...", filename)
            return _download_all_and_regenerate()

    # Compare remote content hash with stored hash
    needs_update = False
    for filename, urls in _SOURCES.items():
        try:
            req = urllib.request.Request(urls["raw_url"])
            with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT) as resp:
                remote_content = resp.read()
                remote_hash = hashlib.sha256(remote_content).hexdigest()[:_SHA_HASH_LENGTH]
                stored_hash = stored_hashes.get(filename, "")
                
                if remote_hash != stored_hash:
                    # Content changed, save file
                    dest = _DATA_DIR / filename
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(remote_content)
                    needs_update = True
                    logger.debug("Updated %s (content changed)", filename)
                else:
                    logger.debug("%s is up to date", filename)
        except urllib.error.URLError as e:
            logger.error("Failed to check %s: %s", filename, e)
            return False

    if not needs_update:
        logger.debug("All files up to date, no regeneration needed.")
        return False

    # Regenerate JSON with new content
    generate_json()
    return True


def _download_all_and_regenerate() -> bool:
    """Download all source files and regenerate JSON."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    all_ok = True
    for filename, urls in _SOURCES.items():
        dest = _DATA_DIR / filename
        logger.debug("Downloading %s...", filename)
        if not _download_file(urls["raw_url"], dest):
            all_ok = False

    if all_ok:
        generate_json()
    else:
        logger.error("Some downloads failed. JSON not regenerated.")
    return all_ok


# ═══════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════

# Module-level cache with thread-safety
_cache: Optional[dict] = None
_cache_lock = threading.Lock()


def _load_cache() -> dict:
    """Load and cache settings_wiki.json (thread-safe)."""
    global _cache
    
    # Fast path: cache already loaded (no lock needed)
    if _cache is not None:
        return _cache
    
    with _cache_lock:
        # Double-check after acquiring lock
        if _cache is not None:
            return _cache

        if not _JSON_PATH.exists():
            logger.debug("settings_wiki.json not found, building from .cpp files")
            if (_DATA_DIR / "Tab.cpp").exists() and (_DATA_DIR / "PrintConfig.cpp").exists():
                generate_json()
            else:
                logger.warning(
                    "No data files found. Run 'python settings_wiki.py' to download and generate."
                )
                _cache = {"_meta": {}, "settings": {}}
                return _cache

        try:
            with open(_JSON_PATH, 'r', encoding='utf-8') as f:
                _cache = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load settings_wiki.json: %s", e)
            logger.warning(
                "Wiki links will be unavailable. "
                "Run 'python analyze.py --update-wiki' to fix."
            )
            _cache = {"_meta": {}, "settings": {}}

        return _cache


def get_wiki_url(setting_key: str) -> Optional[str]:
    """Return the full wiki URL for a setting key, or None if not found.

    Args:
        setting_key: The OrcaSlicer setting key (e.g., 'layer_height').

    Returns:
        Full URL to the wiki page, or None.
    """
    data = _load_cache()
    info = data.get("settings", {}).get(setting_key)
    if info and "wiki_page" in info:
        wiki_base = data.get("_meta", {}).get("wiki_base", WIKI_BASE)
        return f"{wiki_base}{info['wiki_page']}"
    return None


def get_setting_info(setting_key: str) -> Optional[dict]:
    """Return full metadata for a setting key.

    Args:
        setting_key: The OrcaSlicer setting key (e.g., 'layer_height').

    Returns:
        Dict with keys like label, category, tooltip, sidetext, type, default,
        wiki_page. Returns None if setting not found.
    """
    data = _load_cache()
    return data.get("settings", {}).get(setting_key)


def get_all_settings() -> dict:
    """Return the full settings dictionary."""
    data = _load_cache()
    return data.get("settings", {})


def get_meta() -> dict:
    """Return the metadata from settings_wiki.json."""
    data = _load_cache()
    return data.get("_meta", {})


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    """CLI entry point: update data files from GitHub and regenerate JSON."""
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    import argparse
    parser = argparse.ArgumentParser(
        description="OrcaSlicer settings reference - download and parse source files"
    )
    parser.add_argument(
        '--force', '-f', action='store_true',
        help='Force re-download even if files appear up to date'
    )
    parser.add_argument(
        '--parse-only', action='store_true',
        help='Only regenerate JSON from existing .cpp files (no download)'
    )
    args = parser.parse_args()

    if args.parse_only:
        if not (_DATA_DIR / "Tab.cpp").exists() or not (_DATA_DIR / "PrintConfig.cpp").exists():
            logger.error("Source files not found in %s. Run without --parse-only first.", _DATA_DIR)
            sys.exit(1)
        path = generate_json()
        print(f"Generated: {path}")
        sys.exit(0)
    
    try:
        updated = update(force=args.force)
        if updated:
            print("Wiki data updated successfully.")
            sys.exit(0)
        else:
            print("Wiki data is already up to date.")
            sys.exit(0)
    except Exception as e:
        logger.error("Failed to update wiki data: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
