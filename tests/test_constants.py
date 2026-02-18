"""Unit tests for core.constants module."""

from core.constants import (
    BOOL_FALSE,
    BOOL_TRUE,
    DEFAULT_EXTRUDER,
    DEFAULT_IDENTIFY_ID,
    FILE_EXTENSION_3MF,
    FILE_EXTENSION_GCODE,
    FILAMENT_COLORS,
    GCODE_CONFIG_END,
    GCODE_CONFIG_START,
    GCODE_HEADER_END,
    GCODE_HEADER_START,
    GCODE_OBJECT_MARKER,
    INFILL_DENSITY_KEYS,
    PLATE_COLORS,
    SYSTEM_KEYS,
)


class TestConstants:
    """Tests to verify constants are properly defined."""

    def test_bool_constants(self):
        """Boolean string constants should be correct."""
        assert BOOL_TRUE == '1'
        assert BOOL_FALSE == '0'

    def test_default_extruder(self):
        """Default extruder should be '1'."""
        assert DEFAULT_EXTRUDER == '1'

    def test_system_keys_is_frozenset(self):
        """SYSTEM_KEYS should be a frozenset for performance."""
        assert isinstance(SYSTEM_KEYS, frozenset)
        assert 'name' in SYSTEM_KEYS
        assert 'matrix' in SYSTEM_KEYS

    def test_infill_density_keys(self):
        """Infill density keys should include both variants."""
        assert 'sparse_infill_density' in INFILL_DENSITY_KEYS
        assert 'skeleton_infill_density' in INFILL_DENSITY_KEYS


class TestConstantsExtended:
    """Extended tests for remaining constants."""

    def test_default_identify_id(self):
        """DEFAULT_IDENTIFY_ID should be integer 0."""
        assert DEFAULT_IDENTIFY_ID == 0
        assert isinstance(DEFAULT_IDENTIFY_ID, int)

    def test_file_extensions(self):
        """File extension constants should be lowercase with leading dot."""
        assert FILE_EXTENSION_3MF == '.3mf'
        assert FILE_EXTENSION_GCODE == '.gcode'

    def test_filament_colors_non_empty_tuple(self):
        """FILAMENT_COLORS should be a non-empty tuple of strings."""
        assert isinstance(FILAMENT_COLORS, tuple)
        assert len(FILAMENT_COLORS) >= 1
        assert all(isinstance(c, str) for c in FILAMENT_COLORS)

    def test_plate_colors_non_empty_tuple(self):
        """PLATE_COLORS should be a non-empty tuple of strings."""
        assert isinstance(PLATE_COLORS, tuple)
        assert len(PLATE_COLORS) >= 1
        assert all(isinstance(c, str) for c in PLATE_COLORS)

    def test_gcode_block_markers_are_comment_strings(self):
        """Gcode block markers should be comment strings starting with '; '."""
        for marker in (GCODE_HEADER_START, GCODE_HEADER_END,
                       GCODE_CONFIG_START, GCODE_CONFIG_END):
            assert marker.startswith('; '), f"Marker '{marker}' should start with '; '"

    def test_gcode_object_marker(self):
        """GCODE_OBJECT_MARKER should be the standard object comment prefix."""
        assert GCODE_OBJECT_MARKER == '; printing object '
