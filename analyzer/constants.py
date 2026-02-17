"""Shared constants for the 3MF Settings Analyzer."""

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

# File extensions
FILE_EXTENSION_3MF = '.3mf'
FILE_EXTENSION_GCODE = '.gcode'

# Gcode block markers
GCODE_HEADER_START = '; HEADER_BLOCK_START'
GCODE_HEADER_END = '; HEADER_BLOCK_END'
GCODE_CONFIG_START = '; CONFIG_BLOCK_START'
GCODE_CONFIG_END = '; CONFIG_BLOCK_END'
GCODE_OBJECT_MARKER = '; printing object '
