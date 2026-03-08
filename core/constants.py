"""Shared constants for the 3MF Settings Analyzer."""

from typing import Any, Callable, Dict

# System metadata keys that are not custom print settings
SYSTEM_KEYS = frozenset({
    'name', 'matrix', 'extruder', 'face_count',
    'source_object_id', 'source_volume_id',
    'source_offset_x', 'source_offset_y', 'source_offset_z'
})

# Boolean string values used in 3MF configs
BOOL_TRUE = '1'
BOOL_FALSE = '0'

# Infill density setting keys (skeleton_infill_density is legacy alias)
INFILL_DENSITY_KEYS = ('sparse_infill_density', 'skeleton_infill_density')

# Filament colors by number for table display
FILAMENT_COLORS = ('cyan', 'magenta', 'green', 'yellow', 'blue', 'red')

# Plate colors - distinct from filament colors, all clearly visible on dark bg
PLATE_COLORS = (
    'bright_white', 'dark_orange', 'wheat1', 'orchid',
    'turquoise2', 'salmon1', 'chartreuse3', 'deep_sky_blue1',
    'medium_purple1', 'gold1',
)

# Default extruder number (first extruder)
DEFAULT_EXTRUDER = '1'

# Fallback for sorting when identify_id is missing or invalid
DEFAULT_IDENTIFY_ID = 0

# Parsing limits
HEADER_LINES_LIMIT = 100  # Max lines to scan for gcode header block
TAIL_READ_SIZE = 100_000  # Bytes to read from end of gcode file for config block

# CLI limits
MAX_COMPARE_FILES = 4  # Maximum files for comparison mode

# Output formatting widths
LABEL_WIDTH = 34  # Label column width in comparison tables
SINGLE_LABEL_WIDTH = 31  # Label column width in single-file tables

# File extensions
FILE_EXTENSION_3MF = '.3mf'
FILE_EXTENSION_GCODE = '.gcode'

# Gcode block markers
GCODE_HEADER_START = '; HEADER_BLOCK_START'
GCODE_HEADER_END = '; HEADER_BLOCK_END'
GCODE_CONFIG_START = '; CONFIG_BLOCK_START'
GCODE_CONFIG_END = '; CONFIG_BLOCK_END'
GCODE_OBJECT_MARKER = '; printing object '
GCODE_THUMBNAIL_START = '; thumbnail begin'
GCODE_THUMBNAIL_END = '; thumbnail end'

# Gcode parsing configuration - what sections to process
GCODE_PARSE_CONFIG = {
    'parse_headers': True,           # Parse header metadata (slicer version, etc.)
    'skip_thumbnails': True,         # Skip base64-encoded preview images
    'extract_objects': True,         # Extract object names from markers
    'skip_gcode_commands': True,     # Skip G-code movement commands (future: 3D preview)
    'parse_statistics': True,        # Parse statistics (filament usage, time, etc.)
    'parse_config': True,            # Parse CONFIG_BLOCK settings
}

# Max line length for safety (malformed files protection)
MAX_GCODE_LINE_LENGTH = 10_000  # G-code commands are typically < 200 chars

# Common profile setting keys shared by ThreeMFAnalyzer and GcodeAnalyzer.
# Each tuple is (output_key, source_key) -- both analyzers read from the same
# slicer key names for these settings.  The few settings that differ between
# 3MF and Gcode formats are handled individually in each analyzer.
COMMON_PROFILE_KEYS: tuple = (
    # Basic
    ('layer_height', 'layer_height'),
    ('nozzle', 'nozzle_diameter'),
    ('line_width', 'line_width'),
    ('wall_loops', 'wall_loops'),
    ('sparse_infill_density', 'sparse_infill_density'),
    ('brim_type', 'brim_type'),
    ('enable_support', 'enable_support'),
    # Flow
    ('print_flow_ratio', 'print_flow_ratio'),
    ('filament_flow_ratio', 'filament_flow_ratio'),
    # Speeds
    ('initial_layer_speed', 'initial_layer_speed'),
    ('outer_wall_speed', 'outer_wall_speed'),
    ('inner_wall_speed', 'inner_wall_speed'),
    ('sparse_infill_speed', 'sparse_infill_speed'),
    ('top_surface_speed', 'top_surface_speed'),
    ('travel_speed', 'travel_speed'),
    ('bridge_speed', 'bridge_speed'),
    # Shells
    ('top_shell_layers', 'top_shell_layers'),
    ('bottom_shell_layers', 'bottom_shell_layers'),
    # Seams
    ('seam_position', 'seam_position'),
    # Patterns
    ('sparse_infill_pattern', 'sparse_infill_pattern'),
    ('top_surface_pattern', 'top_surface_pattern'),
    # Special modes
    ('ironing_type', 'ironing_type'),
    ('fuzzy_skin', 'fuzzy_skin'),
    ('spiral_mode', 'spiral_mode'),
    # Retraction and Z
    ('retraction_length', 'retraction_length'),
    ('retraction_speed', 'retraction_speed'),
    ('z_hop', 'z_hop'),
    # Fan
    ('fan_min_speed', 'fan_min_speed'),
    ('fan_max_speed', 'fan_max_speed'),
    # Cooling
    ('slow_down_for_layer_cooling', 'slow_down_for_layer_cooling'),
    ('slow_down_layer_time', 'slow_down_layer_time'),
    # Advanced
    ('pressure_advance', 'pressure_advance'),
    ('enable_arc_fitting', 'enable_arc_fitting'),
    ('enable_overhang_speed', 'enable_overhang_speed'),
    # Print modes
    ('print_sequence', 'print_sequence'),
    ('timelapse_type', 'timelapse_type'),
    # Supports
    ('support_type', 'support_type'),
    ('support_threshold_angle', 'support_threshold_angle'),
    ('support_top_z_distance', 'support_top_z_distance'),
    ('support_bottom_z_distance', 'support_bottom_z_distance'),
    # Temperatures
    ('first_layer_nozzle_temperature', 'nozzle_temperature_initial_layer'),
    ('first_layer_bed_temperature', 'hot_plate_temp_initial_layer'),
    ('nozzle_temperature', 'nozzle_temperature'),
    ('bed_temperature', 'hot_plate_temp'),
    # Flow limits
    ('filament_max_volumetric_speed', 'filament_max_volumetric_speed'),
)


def build_common_profile(getter: Callable[..., Any]) -> Dict[str, Any]:
    """Build profile dict from COMMON_PROFILE_KEYS using the provided getter.

    Args:
        getter: Callable with signature (key, default) -> value.
                Typically ``self._get_value`` from an analyzer class.

    Returns:
        Dict with profile settings populated via the getter.
    """
    return {out_key: getter(src_key, '') for out_key, src_key in COMMON_PROFILE_KEYS}
