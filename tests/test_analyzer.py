"""Unit tests for analyze.py module."""

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

# Import module under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from analyze import (
    ThreeMFAnalyzer,
    _is_custom,
    BOOL_TRUE,
    BOOL_FALSE,
    DEFAULT_EXTRUDER,
    SYSTEM_KEYS,
    INFILL_DENSITY_KEYS,
)


# ═══════════════════════════════════════════════════════════════
# Test _is_custom helper function
# ═══════════════════════════════════════════════════════════════

class TestIsCustom:
    """Tests for the _is_custom helper function."""

    def test_none_value_returns_false(self):
        """None object value should not be considered custom."""
        assert _is_custom(None, "any_value") is False

    def test_same_values_returns_false(self):
        """Identical values should not be considered custom."""
        assert _is_custom("10", "10") is False
        assert _is_custom(10, 10) is False
        assert _is_custom("0.2", "0.2") is False

    def test_different_values_returns_true(self):
        """Different values should be considered custom."""
        assert _is_custom("15", "10") is True
        assert _is_custom("0.3", "0.2") is True

    def test_string_number_comparison(self):
        """String and number with same value should match after str()."""
        assert _is_custom(10, "10") is False
        assert _is_custom("10", 10) is False

    def test_empty_string_vs_none(self):
        """Empty string is a valid value, not None."""
        assert _is_custom("", "default") is True


# ═══════════════════════════════════════════════════════════════
# Test Zip Slip protection
# ═══════════════════════════════════════════════════════════════

class TestZipSlipProtection:
    """Tests for Zip Slip security protection."""

    def test_rejects_absolute_path(self, malicious_3mf_absolute_path: Path):
        """Analyzer should reject 3MF files with absolute paths."""
        analyzer = ThreeMFAnalyzer(malicious_3mf_absolute_path)
        
        with pytest.raises(ValueError, match="Unsafe absolute path"):
            analyzer.analyze()

    def test_rejects_path_traversal(self, malicious_3mf_traversal: Path):
        """Analyzer should reject 3MF files with path traversal sequences."""
        analyzer = ThreeMFAnalyzer(malicious_3mf_traversal)
        
        with pytest.raises(ValueError, match="Path traversal detected"):
            analyzer.analyze()

    def test_cleans_up_on_security_error(self, malicious_3mf_traversal: Path):
        """Temporary directory should be cleaned up after security error."""
        analyzer = ThreeMFAnalyzer(malicious_3mf_traversal)
        
        with pytest.raises(ValueError):
            analyzer.analyze()
        
        # Temp dir should be cleaned up
        assert analyzer.temp_dir is None or not analyzer.temp_dir.exists()


# ═══════════════════════════════════════════════════════════════
# Test ThreeMFAnalyzer
# ═══════════════════════════════════════════════════════════════

class TestThreeMFAnalyzer:
    """Tests for the main ThreeMFAnalyzer class."""

    def test_accepts_string_path(self, sample_3mf: Path):
        """Analyzer should accept string filepath."""
        analyzer = ThreeMFAnalyzer(str(sample_3mf))
        assert analyzer.filepath == sample_3mf

    def test_accepts_path_object(self, sample_3mf: Path):
        """Analyzer should accept Path object."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        assert analyzer.filepath == sample_3mf

    def test_analyze_returns_dict(self, sample_3mf: Path):
        """analyze() should return a dictionary with expected keys."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        result = analyzer.analyze()
        
        assert isinstance(result, dict)
        assert 'file' in result
        assert 'profile' in result
        assert 'profile_full' in result
        assert 'custom_global' in result
        assert 'rows' in result

    def test_analyze_extracts_profile_info(self, sample_3mf: Path):
        """analyze() should extract profile information correctly."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        result = analyzer.analyze()
        
        profile = result['profile']
        assert profile['printer'] == "Bambu Lab A1 mini 0.4 nozzle"
        assert profile['process'] == "0.20mm Standard @BBL A1M"
        assert "Bambu PLA Basic @BBL A1M" in profile['filaments']

    def test_analyze_extracts_objects(self, sample_3mf: Path):
        """analyze() should extract object information."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        result = analyzer.analyze()
        
        rows = result['rows']
        assert len(rows) >= 1
        
        # Find the TestObject
        test_obj = next((r for r in rows if r['name'] == 'TestObject'), None)
        assert test_obj is not None
        assert test_obj['wall_loops'] == '4'  # Custom value from XML
        assert test_obj['walls_custom'] is True

    def test_analyze_handles_empty_3mf(self, empty_3mf: Path):
        """analyze() should handle 3MF files without configs gracefully."""
        analyzer = ThreeMFAnalyzer(empty_3mf)
        result = analyzer.analyze()
        
        assert result['profile']['printer'] == 'Unknown'
        assert result['rows'] == []

    def test_analyze_cleanup_on_success(self, sample_3mf: Path):
        """Temporary files should be cleaned up after successful analysis."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        result = analyzer.analyze()
        
        # After analysis, temp_dir should be cleaned
        assert analyzer.temp_dir is None or not analyzer.temp_dir.exists()


# ═══════════════════════════════════════════════════════════════
# Test error handling
# ═══════════════════════════════════════════════════════════════

class TestErrorHandling:
    """Tests for error handling scenarios."""

    def test_invalid_json_raises_error(self, invalid_json_3mf: Path):
        """Invalid JSON in project_settings should raise JSONDecodeError."""
        analyzer = ThreeMFAnalyzer(invalid_json_3mf)
        
        with pytest.raises(json.JSONDecodeError):
            analyzer.analyze()

    def test_invalid_xml_raises_error(self, invalid_xml_3mf: Path):
        """Invalid XML in model_settings should raise ParseError."""
        analyzer = ThreeMFAnalyzer(invalid_xml_3mf)
        
        # This will raise ET.ParseError (or xml.etree.ElementTree.ParseError)
        with pytest.raises(Exception):  # ParseError inheritance varies
            analyzer.analyze()

    def test_nonexistent_file_raises_error(self, temp_dir: Path):
        """Non-existent file should raise appropriate error."""
        fake_path = temp_dir / "nonexistent.3mf"
        analyzer = ThreeMFAnalyzer(fake_path)
        
        with pytest.raises(OSError):
            analyzer.analyze()

    def test_invalid_zip_raises_error(self, temp_dir: Path):
        """Invalid ZIP file should raise BadZipFile error."""
        not_a_zip = temp_dir / "not_a_zip.3mf"
        not_a_zip.write_text("This is not a ZIP file")
        
        analyzer = ThreeMFAnalyzer(not_a_zip)
        
        with pytest.raises(zipfile.BadZipFile):
            analyzer.analyze()


# ═══════════════════════════════════════════════════════════════
# Test _get_value method
# ═══════════════════════════════════════════════════════════════

class TestGetValue:
    """Tests for the _get_value method."""

    def test_get_simple_value(self, sample_3mf: Path):
        """Should return simple string values."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        analyzer.analyze()  # Populates project_settings
        
        # Access internal method for testing
        assert analyzer._get_value('layer_height') == '0.2'

    def test_get_list_value_first_element(self, sample_3mf: Path):
        """Should return first element of list by default."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        analyzer.analyze()
        
        # filament_settings_id is a list
        value = analyzer._get_value('filament_settings_id')
        assert value == "Bambu PLA Basic @BBL A1M"

    def test_get_list_value_entire_list(self, sample_3mf: Path):
        """Should return entire list when index=-1."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        analyzer.analyze()
        
        value = analyzer._get_value('filament_settings_id', index=-1)
        assert isinstance(value, list)

    def test_get_missing_key_returns_default(self, sample_3mf: Path):
        """Missing key should return default value."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        analyzer.analyze()
        
        value = analyzer._get_value('nonexistent_key', default='fallback')
        assert value == 'fallback'


# ═══════════════════════════════════════════════════════════════
# Test format functions
# ═══════════════════════════════════════════════════════════════

class TestFormatFunctions:
    """Tests for formatting helper functions."""

    def test_format_brim_mapping(self, sample_3mf: Path):
        """_format_brim should correctly map brim types."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        
        assert analyzer._format_brim('no_brim') == 'No'
        assert analyzer._format_brim('brim_ears') == 'Mouse ear'
        assert analyzer._format_brim('outer_only') == 'Outer'
        assert analyzer._format_brim('inner_only') == 'Inner'
        assert analyzer._format_brim('outer_and_inner') == 'Both'

    def test_format_brim_unknown(self, sample_3mf: Path):
        """_format_brim should return unknown types as-is."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        
        assert analyzer._format_brim('some_new_type') == 'some_new_type'

    def test_format_brim_empty(self, sample_3mf: Path):
        """_format_brim should return empty string for empty input."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        
        assert analyzer._format_brim('') == ''
        assert analyzer._format_brim(None) == ''

    def test_format_infill_removes_percent(self, sample_3mf: Path):
        """_format_infill should remove % sign."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        
        assert analyzer._format_infill('15%') == '15'
        assert analyzer._format_infill('100%') == '100'

    def test_format_infill_handles_none(self, sample_3mf: Path):
        """_format_infill should return empty string for None."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        
        assert analyzer._format_infill(None) == ''

    def test_format_infill_handles_numeric(self, sample_3mf: Path):
        """_format_infill should handle numeric values."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        
        assert analyzer._format_infill(15) == '15'
        assert analyzer._format_infill(0) == '0'


# ═══════════════════════════════════════════════════════════════
# Test constants
# ═══════════════════════════════════════════════════════════════

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
