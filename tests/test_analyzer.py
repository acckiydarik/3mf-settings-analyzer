"""Unit tests for analyze.py module."""

import json
import sys
import zipfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from xml.etree.ElementTree import ParseError

import pytest

from analyze import (
    ThreeMFAnalyzer,
    GcodeAnalyzer,
    _is_custom,
    _format_object_value,
    _format_support_value,
    _format_file_size,
    _format_filament_list,
    _hex_to_color_name,
    _load_css3_colors,
    _find_nearest_css3_color,
    _get_file_type,
    main,
    print_results,
    print_gcode_results,
    setup_logging,
    BOOL_TRUE,
    BOOL_FALSE,
    DEFAULT_EXTRUDER,
    SYSTEM_KEYS,
    INFILL_DENSITY_KEYS,
    FILE_EXTENSION_3MF,
    FILE_EXTENSION_GCODE,
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
        
        with pytest.raises(ParseError):
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
# Test _get_custom_global_settings method
# ═══════════════════════════════════════════════════════════════

class TestGetCustomGlobalSettings:
    """Tests for the _get_custom_global_settings method."""

    def test_returns_dict(self, sample_3mf: Path):
        """_get_custom_global_settings should return a dictionary."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        analyzer.analyze()
        
        custom = analyzer._get_custom_global_settings()
        assert isinstance(custom, dict)

    def test_extracts_diff_settings(self, sample_3mf: Path):
        """Should extract settings listed in different_settings_to_system."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        analyzer.analyze()
        
        custom = analyzer._get_custom_global_settings()
        # sample_project_settings has different_settings_to_system: ["wall_loops;seam_position"]
        assert 'wall_loops' in custom
        assert 'seam_position' in custom
        assert custom['wall_loops'] == '3'
        assert custom['seam_position'] == 'back'

    def test_unwraps_single_element_list(self, temp_dir: Path, sample_model_settings_xml: str):
        """Should unwrap single-element lists to their value."""
        project_settings = {
            "printer_settings_id": "Test Printer",
            "print_settings_id": "Test Process",
            "filament_settings_id": ["Test Filament"],
            "some_setting": ["single_value"],
            "different_settings_to_system": ["some_setting"],
        }
        
        threemf_path = temp_dir / "unwrap_test.3mf"
        with zipfile.ZipFile(threemf_path, 'w') as zf:
            zf.writestr("Metadata/project_settings.config", json.dumps(project_settings))
            zf.writestr("Metadata/model_settings.config", sample_model_settings_xml)
        
        analyzer = ThreeMFAnalyzer(threemf_path)
        analyzer.analyze()
        
        custom = analyzer._get_custom_global_settings()
        # Single-element list should be unwrapped
        assert custom['some_setting'] == 'single_value'

    def test_handles_empty_diff_settings(self, temp_dir: Path, sample_model_settings_xml: str):
        """Should return empty dict when different_settings_to_system is empty."""
        project_settings = {
            "printer_settings_id": "Test Printer",
            "print_settings_id": "Test Process",
            "filament_settings_id": ["Test Filament"],
            "different_settings_to_system": [""],
        }
        
        threemf_path = temp_dir / "empty_diff_test.3mf"
        with zipfile.ZipFile(threemf_path, 'w') as zf:
            zf.writestr("Metadata/project_settings.config", json.dumps(project_settings))
            zf.writestr("Metadata/model_settings.config", sample_model_settings_xml)
        
        analyzer = ThreeMFAnalyzer(threemf_path)
        analyzer.analyze()
        
        custom = analyzer._get_custom_global_settings()
        assert custom == {}

    def test_handles_missing_diff_settings(self, temp_dir: Path, sample_model_settings_xml: str):
        """Should return empty dict when different_settings_to_system is missing."""
        project_settings = {
            "printer_settings_id": "Test Printer",
            "print_settings_id": "Test Process",
            "filament_settings_id": ["Test Filament"],
        }
        
        threemf_path = temp_dir / "no_diff_test.3mf"
        with zipfile.ZipFile(threemf_path, 'w') as zf:
            zf.writestr("Metadata/project_settings.config", json.dumps(project_settings))
            zf.writestr("Metadata/model_settings.config", sample_model_settings_xml)
        
        analyzer = ThreeMFAnalyzer(threemf_path)
        analyzer.analyze()
        
        custom = analyzer._get_custom_global_settings()
        assert custom == {}


# ═══════════════════════════════════════════════════════════════
# Test format functions
# ═══════════════════════════════════════════════════════════════

class TestFormatFunctions:
    """Tests for formatting helper functions."""

    @pytest.mark.parametrize("input_val,expected", [
        ('no_brim', 'No'),
        ('brim_ears', 'Mouse ear'),
        ('outer_only', 'Outer'),
        ('inner_only', 'Inner'),
        ('outer_and_inner', 'Both'),
        ('some_new_type', 'some_new_type'),
        ('', ''),
        (None, ''),
    ])
    def test_format_brim(self, sample_3mf: Path, input_val, expected):
        """_format_brim should correctly map brim types."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        assert analyzer._format_brim(input_val) == expected

    @pytest.mark.parametrize("input_val,expected", [
        ('15%', '15'),
        ('100%', '100'),
        ('0%', '0'),
        (15, '15'),
        (0, '0'),
        (None, ''),
    ])
    def test_format_infill(self, sample_3mf: Path, input_val, expected):
        """_format_infill should handle various input types."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        assert analyzer._format_infill(input_val) == expected


# ═══════════════════════════════════════════════════════════════
# Test _format_object_value function
# ═══════════════════════════════════════════════════════════════

class TestFormatObjectValue:
    """Tests for _format_object_value helper function."""

    def test_empty_value_returns_empty_string(self):
        """Empty/None value should return empty string."""
        assert _format_object_value(None, False, 'default', False) == ''
        assert _format_object_value('', False, 'default', False) == ''
        assert _format_object_value(0, False, 'default', False) == ''

    def test_regular_value_no_custom(self):
        """Non-custom value should return plain string."""
        assert _format_object_value('10', False, '10', False) == '10'
        assert _format_object_value(15, False, '15', False) == '15'

    def test_custom_value_without_diff(self):
        """Custom value without diff mode should show asterisk."""
        result = _format_object_value('20', True, '10', False)
        assert '*20' in result
        assert 'bold yellow' in result
        assert '←' not in result

    def test_custom_value_with_diff(self):
        """Custom value with diff mode should show asterisk and default."""
        result = _format_object_value('20', True, '10', True)
        assert '*20' in result
        assert '←10' in result
        assert 'bold yellow' in result

    def test_custom_value_diff_no_default(self):
        """Custom value with diff but no default should not show arrow."""
        result = _format_object_value('20', True, None, True)
        assert '*20' in result
        assert '←' not in result

    def test_custom_value_diff_empty_default(self):
        """Custom value with empty default should not show arrow."""
        result = _format_object_value('20', True, '', True)
        assert '*20' in result
        assert '←' not in result


# ═══════════════════════════════════════════════════════════════
# Test _format_support_value function
# ═══════════════════════════════════════════════════════════════

class TestFormatSupportValue:
    """Tests for _format_support_value helper function."""

    def test_empty_value_returns_empty_string(self):
        """Empty support value should return empty string."""
        assert _format_support_value('', False) == ''
        assert _format_support_value('', True) == ''

    def test_support_on_not_custom(self):
        """Support On (not custom) should be green."""
        result = _format_support_value('On', False)
        assert 'On' in result
        assert 'green' in result
        assert '*' not in result

    def test_support_on_custom(self):
        """Support On (custom) should show asterisk in yellow."""
        result = _format_support_value('On', True)
        assert '*On' in result
        assert 'bold yellow' in result

    def test_support_off_not_custom(self):
        """Support Off (not custom) should be dim."""
        result = _format_support_value('Off', False)
        assert 'Off' in result
        assert 'dim' in result
        assert '*' not in result

    def test_support_off_custom(self):
        """Support Off (custom) should show asterisk in yellow."""
        result = _format_support_value('Off', True)
        assert '*Off' in result
        assert 'bold yellow' in result


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


# ═══════════════════════════════════════════════════════════════
# Test CLI / main() function
# ═══════════════════════════════════════════════════════════════

class TestCLI:
    """Tests for command-line interface and main() function."""

    def test_main_with_file(self, sample_3mf: Path):
        """main() should work with a valid 3MF file."""
        with patch.object(sys, 'argv', ['analyze.py', str(sample_3mf)]):
            # Should not raise an exception
            main()

    def test_main_json_output(self, sample_3mf: Path, capsys):
        """--json flag should output valid JSON."""
        with patch.object(sys, 'argv', ['analyze.py', str(sample_3mf), '--json']):
            main()
        
        captured = capsys.readouterr()
        # Verify output is valid JSON
        data = json.loads(captured.out)
        assert 'file' in data
        assert 'profile' in data
        assert 'rows' in data

    def test_main_diff_mode(self, sample_3mf: Path, capsys):
        """--diff flag should not cause errors."""
        with patch.object(sys, 'argv', ['analyze.py', str(sample_3mf), '--diff']):
            main()
        
        # Output should contain something (table output)
        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_main_no_color(self, sample_3mf: Path):
        """--no-color flag should work without errors."""
        with patch.object(sys, 'argv', ['analyze.py', str(sample_3mf), '--no-color']):
            main()

    def test_main_wiki_mode(self, sample_3mf: Path):
        """--wiki flag should work without errors."""
        with patch.object(sys, 'argv', ['analyze.py', str(sample_3mf), '--wiki']):
            main()

    def test_main_verbose_mode(self, sample_3mf: Path):
        """--verbose flag should enable debug logging."""
        with patch.object(sys, 'argv', ['analyze.py', str(sample_3mf), '--verbose']):
            main()

    def test_main_combined_flags(self, sample_3mf: Path, capsys):
        """Multiple flags should work together."""
        with patch.object(sys, 'argv', ['analyze.py', str(sample_3mf), '--diff', '--wiki', '--no-color']):
            main()
        
        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_main_missing_file_exits(self):
        """main() should exit with error if no file provided."""
        with patch.object(sys, 'argv', ['analyze.py']):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code != 0

    def test_main_nonexistent_file_exits(self, temp_dir: Path):
        """main() should exit with error for non-existent file."""
        fake_path = temp_dir / "does_not_exist.3mf"
        with patch.object(sys, 'argv', ['analyze.py', str(fake_path)]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_main_bad_zip_exits(self, temp_dir: Path):
        """main() should exit with error for invalid ZIP file."""
        bad_file = temp_dir / "bad.3mf"
        bad_file.write_text("not a zip")
        
        with patch.object(sys, 'argv', ['analyze.py', str(bad_file)]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1


class TestPrintResults:
    """Tests for print_results function."""

    def test_print_results_basic(self, sample_3mf: Path):
        """print_results should not raise with valid data."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        result = analyzer.analyze()
        
        # Should not raise
        print_results(result)

    def test_print_results_diff_mode(self, sample_3mf: Path):
        """print_results with show_diff=True should work."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        result = analyzer.analyze()
        
        print_results(result, show_diff=True)

    def test_print_results_no_color(self, sample_3mf: Path):
        """print_results with no_color=True should work."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        result = analyzer.analyze()
        
        print_results(result, no_color=True)

    def test_print_results_wiki_mode(self, sample_3mf: Path):
        """print_results with wiki=True should work."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        result = analyzer.analyze()
        
        print_results(result, wiki=True)


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_default(self):
        """setup_logging() should set INFO level by default."""
        setup_logging(verbose=False)
        # Just verify no errors

    def test_setup_logging_verbose(self):
        """setup_logging(verbose=True) should set DEBUG level."""
        setup_logging(verbose=True)
        # Just verify no errors


# ═══════════════════════════════════════════════════════════════
# Test Multi-Plate Support
# ═══════════════════════════════════════════════════════════════

class TestMultiPlateSupport:
    """Tests for 3MF files with multiple plates."""

    def test_multi_plate_extraction(self, multi_plate_3mf: Path):
        """Analyzer should extract objects from multiple plates."""
        analyzer = ThreeMFAnalyzer(multi_plate_3mf)
        result = analyzer.analyze()
        
        rows = result['rows']
        assert len(rows) == 3  # 3 objects across 2 plates
        
        # Verify objects are present
        names = [r['name'] for r in rows]
        assert 'Object_Plate1' in names
        assert 'Object_Plate2_First' in names
        assert 'Object_Plate2_Second' in names

    def test_multi_plate_order(self, multi_plate_3mf: Path):
        """Objects should be ordered by plate and identify_id."""
        analyzer = ThreeMFAnalyzer(multi_plate_3mf)
        result = analyzer.analyze()
        
        # The internal plates list should have 2 plates
        assert len(analyzer.plates) == 2
        
        # First plate has 1 object, second has 2
        assert len(analyzer.plates[0]['objects']) == 1
        assert len(analyzer.plates[1]['objects']) == 2


# ═══════════════════════════════════════════════════════════════
# Test Multi-Part Objects
# ═══════════════════════════════════════════════════════════════

class TestMultiPartObjects:
    """Tests for objects with multiple parts."""

    def test_multi_part_extraction(self, multi_part_object_3mf: Path):
        """Analyzer should extract all parts from multi-part object."""
        analyzer = ThreeMFAnalyzer(multi_part_object_3mf)
        result = analyzer.analyze()
        
        rows = result['rows']
        # Should have object + 3 parts = 4 rows
        assert len(rows) >= 3
        
        # Verify parts are present (names may have indentation prefix)
        names = [r['name'].strip() for r in rows]
        assert 'PartA' in names
        assert 'PartB' in names
        assert 'PartC' in names

    def test_part_custom_settings(self, multi_part_object_3mf: Path):
        """Parts should have their own custom settings."""
        analyzer = ThreeMFAnalyzer(multi_part_object_3mf)
        result = analyzer.analyze()
        
        rows = result['rows']
        # Find parts by stripping whitespace from names
        part_a = next((r for r in rows if r['name'].strip() == 'PartA'), None)
        part_b = next((r for r in rows if r['name'].strip() == 'PartB'), None)
        
        assert part_a is not None
        assert part_b is not None
        
        # PartA has 30% infill, PartB has 50% (values may be formatted without %)
        assert '30' in part_a['infill']
        assert '50' in part_b['infill']

    def test_part_extruder_assignment(self, multi_part_object_3mf: Path):
        """Parts can have different extruder assignments."""
        analyzer = ThreeMFAnalyzer(multi_part_object_3mf)
        result = analyzer.analyze()
        
        rows = result['rows']
        # Find parts by stripping whitespace from names
        part_a = next((r for r in rows if r['name'].strip() == 'PartA'), None)
        part_b = next((r for r in rows if r['name'].strip() == 'PartB'), None)
        
        assert part_a is not None
        assert part_b is not None
        # Parts use 'filament' key instead of 'extruder'
        assert part_a.get('filament', part_a.get('extruder')) == '1'
        assert part_b.get('filament', part_b.get('extruder')) == '2'


# ═══════════════════════════════════════════════════════════════
# Test Unicode/Non-ASCII Names
# ═══════════════════════════════════════════════════════════════

class TestUnicodeNames:
    """Tests for Unicode object and part names."""

    def test_unicode_object_name(self, unicode_names_3mf: Path):
        """Analyzer should handle Unicode object names."""
        analyzer = ThreeMFAnalyzer(unicode_names_3mf)
        result = analyzer.analyze()
        
        rows = result['rows']
        assert len(rows) >= 1
        
        # Find object with Unicode name
        obj = next((r for r in rows if 'Тестовый' in r['name']), None)
        assert obj is not None
        assert '测试' in obj['name']

    def test_unicode_part_name(self, unicode_names_3mf: Path):
        """Analyzer should handle Unicode part names."""
        analyzer = ThreeMFAnalyzer(unicode_names_3mf)
        result = analyzer.analyze()
        
        rows = result['rows']
        # Find part with Unicode name (strip whitespace prefix)
        part = next((r for r in rows if r.get('part_id') is not None and 'Часть' in r['name'].strip()), None)
        if part is None:
            # Also try without part_id check, just by name containing Unicode
            part = next((r for r in rows if '日本語' in r['name']), None)
        assert part is not None
        assert '日本語' in part['name']


# ═══════════════════════════════════════════════════════════════
# Test Edge Cases
# ═══════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_list_settings(self, empty_list_settings_3mf: Path):
        """Analyzer should handle empty list values gracefully."""
        analyzer = ThreeMFAnalyzer(empty_list_settings_3mf)
        result = analyzer.analyze()
        
        # Should not raise, filaments should handle empty list
        assert result['profile']['filaments'] == []
        
    def test_get_value_empty_list_with_index(self, empty_list_settings_3mf: Path):
        """_get_value should return default for empty list with index > 0."""
        analyzer = ThreeMFAnalyzer(empty_list_settings_3mf)
        analyzer.analyze()
        
        # Empty list with index should return default
        value = analyzer._get_value('filament_settings_id', default='fallback', index=0)
        assert value == 'fallback'
        
        value = analyzer._get_value('filament_settings_id', default='fallback', index=5)
        assert value == 'fallback'

    def test_non_3mf_extension_warning(self, temp_dir: Path, sample_project_settings: dict, sample_model_settings_xml: str, caplog):
        """File without .3mf extension should still work but may log warning."""
        import logging
        
        # Create file with different extension
        wrong_ext = temp_dir / "test_file.zip"
        with zipfile.ZipFile(wrong_ext, 'w') as zf:
            zf.writestr("Metadata/project_settings.config", json.dumps(sample_project_settings))
            zf.writestr("Metadata/model_settings.config", sample_model_settings_xml)
        
        analyzer = ThreeMFAnalyzer(wrong_ext)
        
        # Should still analyze successfully
        with caplog.at_level(logging.DEBUG):
            result = analyzer.analyze()
        
        assert result['profile']['printer'] == "Bambu Lab A1 mini 0.4 nozzle"


# ═══════════════════════════════════════════════════════════════
# Test GcodeAnalyzer
# ═══════════════════════════════════════════════════════════════

class TestGcodeAnalyzer:
    """Tests for the GcodeAnalyzer class."""

    def test_accepts_string_path(self, sample_gcode: Path):
        """Analyzer should accept string filepath."""
        analyzer = GcodeAnalyzer(str(sample_gcode))
        assert analyzer.filepath == sample_gcode

    def test_accepts_path_object(self, sample_gcode: Path):
        """Analyzer should accept Path object."""
        analyzer = GcodeAnalyzer(sample_gcode)
        assert analyzer.filepath == sample_gcode

    def test_analyze_returns_dict(self, sample_gcode: Path):
        """analyze() should return a dictionary with expected keys."""
        analyzer = GcodeAnalyzer(sample_gcode)
        result = analyzer.analyze()
        
        assert isinstance(result, dict)
        assert 'file' in result
        assert 'profile' in result
        assert 'profile_full' in result
        assert 'custom_global' in result
        assert 'rows' in result
        assert 'objects' in result
        assert 'statistics' in result

    def test_analyze_extracts_profile_info(self, sample_gcode: Path):
        """analyze() should extract profile information correctly."""
        analyzer = GcodeAnalyzer(sample_gcode)
        result = analyzer.analyze()
        
        profile = result['profile']
        assert profile['printer'] == "Snapmaker U1 (0.4 nozzle)"
        assert profile['process'] == "0.16 High Quality @Snapmaker U1 (0.4 nozzle)"
        assert "Snapmaker PLA SnapSpeed @U1" in profile['filaments']

    def test_analyze_extracts_statistics(self, sample_gcode: Path):
        """analyze() should extract print statistics."""
        analyzer = GcodeAnalyzer(sample_gcode)
        result = analyzer.analyze()
        
        stats = result['statistics']
        assert stats['slicer'] == "Snapmaker Orca"
        assert stats['slicer_version'] == "2.2.1"
        assert stats['estimated_time'] == "1h 11m 17s"
        assert stats['total_layers'] == 138
        assert stats['filament_used_g'] == 11.26

    def test_analyze_extracts_filament_cost_per_extruder(self, sample_gcode: Path):
        """analyze() should extract per-extruder filament cost."""
        analyzer = GcodeAnalyzer(sample_gcode)
        result = analyzer.analyze()
        
        stats = result['statistics']
        assert stats['filament_cost_per_extruder'] == [0.20, 0.02, 0.01]
        assert stats['filament_cost'] == 0.23

    def test_analyze_extracts_object_names(self, sample_gcode: Path):
        """analyze() should extract object names from markers."""
        analyzer = GcodeAnalyzer(sample_gcode)
        result = analyzer.analyze()
        
        objects = result['objects']
        assert 'TestModel.stl' in objects
        assert 'SecondObject.stl' in objects
        assert len(objects) == 2

    def test_analyze_extracts_custom_settings(self, sample_gcode: Path):
        """analyze() should extract custom global settings."""
        analyzer = GcodeAnalyzer(sample_gcode)
        result = analyzer.analyze()
        
        custom = result['custom_global']
        assert 'wall_loops' in custom
        assert 'sparse_infill_density' in custom

    def test_analyze_handles_empty_gcode(self, empty_gcode: Path):
        """analyze() should handle empty gcode files."""
        analyzer = GcodeAnalyzer(empty_gcode)
        result = analyzer.analyze()
        
        assert result['profile']['printer'] == 'Unknown'
        assert result['objects'] == []

    def test_analyze_handles_minimal_gcode(self, minimal_gcode: Path):
        """analyze() should handle gcode without CONFIG_BLOCK."""
        analyzer = GcodeAnalyzer(minimal_gcode)
        result = analyzer.analyze()
        
        assert result['profile']['printer'] == 'Unknown'
        assert result['objects'] == []

    def test_analyze_handles_gcode_without_objects(self, gcode_no_objects: Path):
        """analyze() should handle gcode without object markers."""
        analyzer = GcodeAnalyzer(gcode_no_objects)
        result = analyzer.analyze()
        
        assert result['objects'] == []
        stats = result['statistics']
        assert stats['total_layers'] == 50

    def test_analyze_handles_unicode_objects(self, gcode_unicode_objects: Path):
        """analyze() should handle Unicode object names."""
        analyzer = GcodeAnalyzer(gcode_unicode_objects)
        result = analyzer.analyze()
        
        objects = result['objects']
        # Check that the Unicode object name was extracted
        assert any('Тестовый' in obj for obj in objects)

    def test_nonexistent_file_raises_error(self, temp_dir: Path):
        """Non-existent gcode file should raise OSError."""
        fake_path = temp_dir / "nonexistent.gcode"
        analyzer = GcodeAnalyzer(fake_path)
        
        with pytest.raises(OSError):
            analyzer.analyze()


class TestGcodeAnalyzerMethods:
    """Tests for GcodeAnalyzer internal methods."""

    def test_get_value_single(self, sample_gcode: Path):
        """_get_value should return first value from comma-separated list."""
        analyzer = GcodeAnalyzer(sample_gcode)
        analyzer.analyze()
        
        # nozzle_diameter is "0.4,0.4,0.4,0.4" - should return first
        value = analyzer._get_value('nozzle_diameter')
        assert value == '0.4'

    def test_get_value_semicolon_list(self, sample_gcode: Path):
        """_get_value should return first value from semicolon-separated list."""
        analyzer = GcodeAnalyzer(sample_gcode)
        analyzer.analyze()
        
        # filament_type is "PLA;PETG" - should return first
        value = analyzer._get_value('filament_type')
        assert value == 'PLA'

    def test_get_list_value(self, sample_gcode: Path):
        """_get_list_value should return all values as list."""
        analyzer = GcodeAnalyzer(sample_gcode)
        analyzer.analyze()
        
        # filament_type is "PLA;PETG"
        values = analyzer._get_list_value('filament_type')
        assert values == ['PLA', 'PETG']

    def test_get_value_missing_key(self, sample_gcode: Path):
        """_get_value should return default for missing key."""
        analyzer = GcodeAnalyzer(sample_gcode)
        analyzer.analyze()
        
        value = analyzer._get_value('nonexistent_key', default='fallback')
        assert value == 'fallback'


# ═══════════════════════════════════════════════════════════════
# Test _format_file_size function
# ═══════════════════════════════════════════════════════════════

class TestFormatFileSize:
    """Tests for _format_file_size helper function."""

    def test_bytes(self):
        """Should format bytes correctly."""
        assert _format_file_size(100) == "100 B"
        assert _format_file_size(0) == "0 B"

    def test_kilobytes(self):
        """Should format kilobytes correctly."""
        assert _format_file_size(1024) == "1.0 KB"
        assert _format_file_size(2048) == "2.0 KB"
        assert _format_file_size(1536) == "1.5 KB"

    def test_megabytes(self):
        """Should format megabytes correctly."""
        assert _format_file_size(1048576) == "1.00 MB"
        assert _format_file_size(10485760) == "10.00 MB"
        assert _format_file_size(1572864) == "1.50 MB"


# ═══════════════════════════════════════════════════════════════
# Test _get_file_type function
# ═══════════════════════════════════════════════════════════════

class TestGetFileType:
    """Tests for _get_file_type helper function."""

    def test_3mf_extension(self, temp_dir: Path):
        """Should detect .3mf files."""
        path = temp_dir / "test.3mf"
        path.touch()
        assert _get_file_type(path) == '3mf'

    def test_3mf_uppercase(self, temp_dir: Path):
        """Should detect .3MF files (case insensitive)."""
        path = temp_dir / "test.3MF"
        path.touch()
        assert _get_file_type(path) == '3mf'

    def test_gcode_extension(self, temp_dir: Path):
        """Should detect .gcode files."""
        path = temp_dir / "test.gcode"
        path.touch()
        assert _get_file_type(path) == 'gcode'

    def test_gcode_uppercase(self, temp_dir: Path):
        """Should detect .GCODE files (case insensitive)."""
        path = temp_dir / "test.GCODE"
        path.touch()
        assert _get_file_type(path) == 'gcode'

    def test_unknown_extension(self, temp_dir: Path):
        """Should return 'unknown' for other extensions."""
        path = temp_dir / "test.txt"
        path.touch()
        assert _get_file_type(path) == 'unknown'
        
        path2 = temp_dir / "test.stl"
        path2.touch()
        assert _get_file_type(path2) == 'unknown'


# ═══════════════════════════════════════════════════════════════
# Test CLI with Gcode files
# ═══════════════════════════════════════════════════════════════

class TestGcodeCLI:
    """Tests for command-line interface with gcode files."""

    def test_main_with_gcode(self, sample_gcode: Path):
        """main() should work with a valid gcode file."""
        with patch.object(sys, 'argv', ['analyze.py', str(sample_gcode)]):
            main()

    def test_main_gcode_json_output(self, sample_gcode: Path, capsys):
        """--json flag should output valid JSON for gcode."""
        with patch.object(sys, 'argv', ['analyze.py', str(sample_gcode), '--json']):
            main()
        
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert 'file' in data
        assert 'profile' in data
        assert 'statistics' in data
        assert 'objects' in data

    def test_main_gcode_diff_mode(self, sample_gcode: Path, capsys):
        """--diff flag should work with gcode files."""
        with patch.object(sys, 'argv', ['analyze.py', str(sample_gcode), '--diff']):
            main()
        
        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_main_gcode_wiki_mode(self, sample_gcode: Path):
        """--wiki flag should work with gcode files."""
        with patch.object(sys, 'argv', ['analyze.py', str(sample_gcode), '--wiki']):
            main()

    def test_main_unsupported_extension(self, temp_dir: Path):
        """main() should exit with error for unsupported file type."""
        bad_file = temp_dir / "test.stl"
        bad_file.write_text("some content")
        
        with patch.object(sys, 'argv', ['analyze.py', str(bad_file)]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1


class TestPrintGcodeResults:
    """Tests for print_gcode_results function."""

    def test_print_gcode_results_basic(self, sample_gcode: Path):
        """print_gcode_results should not raise with valid data."""
        analyzer = GcodeAnalyzer(sample_gcode)
        result = analyzer.analyze()
        
        # Should not raise
        print_gcode_results(result)

    def test_print_gcode_results_diff_mode(self, sample_gcode: Path):
        """print_gcode_results with show_diff=True should work."""
        analyzer = GcodeAnalyzer(sample_gcode)
        result = analyzer.analyze()
        
        print_gcode_results(result, show_diff=True)

    def test_print_gcode_results_no_color(self, sample_gcode: Path):
        """print_gcode_results with no_color=True should work."""
        analyzer = GcodeAnalyzer(sample_gcode)
        result = analyzer.analyze()
        
        print_gcode_results(result, no_color=True)

    def test_print_gcode_results_wiki_mode(self, sample_gcode: Path):
        """print_gcode_results with wiki=True should work."""
        analyzer = GcodeAnalyzer(sample_gcode)
        result = analyzer.analyze()
        
        print_gcode_results(result, wiki=True)


# ═══════════════════════════════════════════════════════════════
# Test CSS3 color data loading
# ═══════════════════════════════════════════════════════════════

class TestLoadCss3Colors:
    """Tests for CSS3 color data loading."""

    def test_loads_colors_dict(self):
        """Should return a non-empty dict of CSS3 colors."""
        colors = _load_css3_colors()
        assert isinstance(colors, dict)
        assert len(colors) > 100

    def test_colors_have_rgb_values(self):
        """Each color should have a 3-element RGB list."""
        colors = _load_css3_colors()
        for name, rgb in colors.items():
            assert isinstance(rgb, list), f"{name} value is not a list"
            assert len(rgb) == 3, f"{name} has {len(rgb)} elements, expected 3"
            assert all(0 <= v <= 255 for v in rgb), f"{name} has out-of-range values: {rgb}"

    def test_contains_basic_colors(self):
        """Should contain standard basic color names."""
        colors = _load_css3_colors()
        for expected in ('Red', 'Green', 'Blue', 'Yellow', 'White', 'Black',
                         'Orange', 'Purple', 'Pink', 'Gray', 'Cyan', 'Magenta'):
            assert expected in colors, f"Missing basic color: {expected}"

    def test_red_rgb_values(self):
        """CSS3 Red should be [255, 0, 0]."""
        colors = _load_css3_colors()
        assert colors['Red'] == [255, 0, 0]

    def test_caching(self):
        """Second call should return the same object (cached)."""
        colors1 = _load_css3_colors()
        colors2 = _load_css3_colors()
        assert colors1 is colors2


class TestFindNearestCss3Color:
    """Tests for nearest CSS3 color matching."""

    def test_exact_red(self):
        """Exact CSS3 Red (255, 0, 0) should return 'Red'."""
        assert _find_nearest_css3_color(255, 0, 0) == 'Red'

    def test_exact_blue(self):
        """Exact CSS3 Blue (0, 0, 255) should return 'Blue'."""
        assert _find_nearest_css3_color(0, 0, 255) == 'Blue'

    def test_exact_yellow(self):
        """Exact CSS3 Yellow (255, 255, 0) should return 'Yellow'."""
        assert _find_nearest_css3_color(255, 255, 0) == 'Yellow'

    def test_exact_black(self):
        """Exact CSS3 Black (0, 0, 0) should return 'Black'."""
        assert _find_nearest_css3_color(0, 0, 0) == 'Black'

    def test_exact_white(self):
        """Exact CSS3 White (255, 255, 255) should return 'White'."""
        assert _find_nearest_css3_color(255, 255, 255) == 'White'

    def test_gold_amber_matches_gold(self):
        """#F0BE02 (240, 190, 2) should match 'Gold' -- the original bug trigger."""
        name = _find_nearest_css3_color(240, 190, 2)
        assert name == 'Gold'

    def test_near_red_matches_red_family(self):
        """#DE1619 (222, 22, 25) should match a red-family color."""
        name = _find_nearest_css3_color(222, 22, 25)
        assert 'Red' in name or name == 'Crimson' or name == 'Firebrick'

    def test_near_green_matches_green_family(self):
        """#00CC00 should match a green-family color."""
        name = _find_nearest_css3_color(0, 204, 0)
        assert 'Green' in name or name == 'Lime' or name == 'LimeGreen'


# ═══════════════════════════════════════════════════════════════
# Test _hex_to_color_name function
# ═══════════════════════════════════════════════════════════════

class TestHexToColorName:
    """Tests for _hex_to_color_name with CSS3 nearest-match."""

    # --- Exact CSS3 matches ---

    def test_exact_red(self):
        """Pure red #FF0000 should return 'Red'."""
        name, style = _hex_to_color_name('#FF0000FF')
        assert name == 'Red'
        assert style == '#FF0000'

    def test_exact_blue(self):
        """Pure blue #0000FF should return 'Blue'."""
        name, style = _hex_to_color_name('#0000FFFF')
        assert name == 'Blue'
        assert style == '#0000FF'

    def test_exact_yellow(self):
        """Pure yellow #FFFF00 should return 'Yellow'."""
        name, style = _hex_to_color_name('#FFFF00FF')
        assert name == 'Yellow'
        assert style == '#FFFF00'

    def test_exact_black(self):
        """Pure black #000000 should return 'Black'."""
        name, style = _hex_to_color_name('#000000FF')
        assert name == 'Black'
        assert style == '#000000'

    def test_exact_white(self):
        """Pure white #FFFFFF should return 'White'."""
        name, style = _hex_to_color_name('#FFFFFFFF')
        assert name == 'White'
        assert style == '#FFFFFF'

    def test_exact_cyan(self):
        """Exact cyan #00FFFF should return 'Cyan' or 'Aqua'."""
        name, style = _hex_to_color_name('#00FFFFFF')
        assert name in ('Cyan', 'Aqua')
        assert style == '#00FFFF'

    def test_exact_magenta(self):
        """Exact magenta #FF00FF should return 'Magenta' or 'Fuchsia'."""
        name, style = _hex_to_color_name('#FF00FFFF')
        assert name in ('Magenta', 'Fuchsia')
        assert style == '#FF00FF'

    # --- Nearest-match (non-exact) ---

    def test_gold_amber_color(self):
        """#F0BE02 (the original bug) should return 'Gold'."""
        name, style = _hex_to_color_name('#F0BE02FF')
        assert name == 'Gold'
        assert style == '#F0BE02'

    def test_near_red(self):
        """#DE1619 should match a red-family CSS3 color."""
        name, style = _hex_to_color_name('#DE1619FF')
        assert name == 'Crimson'
        assert style == '#DE1619'

    def test_dark_orange(self):
        """#FF8000 should match DarkOrange."""
        name, style = _hex_to_color_name('#FF8000FF')
        assert name == 'DarkOrange'
        assert style == '#FF8000'

    def test_near_green(self):
        """#00CC00 should match a green-family CSS3 color."""
        name, style = _hex_to_color_name('#00CC00FF')
        name_lower = name.lower()
        assert 'green' in name_lower or name == 'Lime'

    def test_near_purple(self):
        """#9900CC should match a purple/violet-family CSS3 color."""
        name, style = _hex_to_color_name('#9900CCFF')
        assert name == 'DarkViolet'
        assert style == '#9900CC'

    def test_pink_shade(self):
        """#FFB0B0 should match a pink-family CSS3 color."""
        name, style = _hex_to_color_name('#FFB0B0FF')
        name_lower = name.lower()
        assert 'pink' in name_lower or 'salmon' in name_lower or 'rose' in name_lower

    def test_gray_shades(self):
        """Various grays should match gray-family CSS3 colors."""
        name, _ = _hex_to_color_name('#808080FF')
        assert name == 'Gray'

        # #505050 is nearest to DarkSlateGray [47,79,79] by RGB distance
        name, _ = _hex_to_color_name('#505050FF')
        assert 'Gray' in name or 'grey' in name.lower() or 'Slate' in name

        name, _ = _hex_to_color_name('#C0C0C0FF')
        assert name == 'Silver'

    # --- Style is always original hex ---

    def test_style_is_hex_for_all_colors(self):
        """Rich style should always be the original hex (truecolor)."""
        test_cases = ['#FF0000FF', '#00FF00', '#0000FF', '#F0BE02FF', '#000000FF']
        for hex_input in test_cases:
            _, style = _hex_to_color_name(hex_input)
            assert style.startswith('#'), f"Style for {hex_input} should start with #, got {style}"
            assert len(style) == 7, f"Style for {hex_input} should be #RRGGBB format, got {style}"

    # --- Format variations ---

    def test_rrggbb_format(self):
        """#RRGGBB without alpha should work."""
        name, style = _hex_to_color_name('#FF0000')
        assert name == 'Red'
        assert style == '#FF0000'

    def test_rrggbbaa_format(self):
        """#RRGGBBAA format should work (alpha ignored)."""
        name, style = _hex_to_color_name('#00FF0080')
        name_lower = name.lower()
        assert 'green' in name_lower or name == 'Lime'
        assert style == '#00FF00'

    # --- Invalid inputs ---

    def test_empty_string(self):
        """Empty string should return itself and 'white' style."""
        name, style = _hex_to_color_name('')
        assert name == ''
        assert style == 'white'

    def test_no_hash_prefix(self):
        """String without # prefix should return itself."""
        name, style = _hex_to_color_name('FF0000')
        assert name == 'FF0000'
        assert style == 'white'

    def test_short_hex(self):
        """Too-short hex should return itself."""
        name, style = _hex_to_color_name('#FFF')
        assert name == '#FFF'
        assert style == 'white'

    def test_non_hex_chars(self):
        """Non-hex characters should be handled gracefully."""
        name, style = _hex_to_color_name('#XYZXYZ')
        assert name == '#XYZXYZ'
        assert style == 'white'

    def test_none_input(self):
        """None should be handled gracefully."""
        name, style = _hex_to_color_name(None)
        assert name is None
        assert style == 'white'

    def test_every_color_gets_a_name(self):
        """No hex color should fall through to raw hex code anymore."""
        test_colors = [
            '#010180FF', '#F0BE02FF', '#A07060FF', '#335577FF',
            '#998877FF', '#AABB00FF', '#123456FF',
        ]
        for hex_input in test_colors:
            name, style = _hex_to_color_name(hex_input)
            assert not name.startswith('#'), (
                f"Color {hex_input} returned raw hex '{name}' instead of a CSS3 name"
            )
            assert style.startswith('#'), f"Style should be hex, got {style}"


# ═══════════════════════════════════════════════════════════════
# Test _format_filament_list function
# ═══════════════════════════════════════════════════════════════

class TestFormatFilamentList:
    """Tests for _format_filament_list helper function."""

    def test_empty_list(self):
        """Empty list should return empty string."""
        assert _format_filament_list([]) == ''

    def test_single_value(self):
        """Single value should return it without separator."""
        assert _format_filament_list([10.5]) == '10.5'

    def test_single_value_with_suffix(self):
        """Single value with suffix should append suffix."""
        assert _format_filament_list([10.5], ' g') == '10.5 g'

    def test_multiple_values(self):
        """Multiple values should be comma-separated."""
        assert _format_filament_list([1, 2, 3]) == '1, 2, 3'

    def test_multiple_values_with_suffix(self):
        """Multiple values with suffix should append suffix to each."""
        result = _format_filament_list(['10.08', '0.87'], ' g')
        assert result == '10.08 g, 0.87 g'

    def test_string_values(self):
        """String values should be formatted correctly."""
        result = _format_filament_list(['PLA', 'PETG'])
        assert result == 'PLA, PETG'


# ═══════════════════════════════════════════════════════════════
# Test GcodeAnalyzerMethods extensions
# ═══════════════════════════════════════════════════════════════

class TestGcodeAnalyzerMethodsExtended:
    """Extended tests for GcodeAnalyzer internal methods."""

    def test_get_list_value_comma_separated(self, sample_gcode: Path):
        """_get_list_value should parse comma-separated values."""
        analyzer = GcodeAnalyzer(sample_gcode)
        analyzer.analyze()

        # nozzle_diameter is "0.4,0.4,0.4,0.4"
        values = analyzer._get_list_value('nozzle_diameter')
        assert values == ['0.4', '0.4', '0.4', '0.4']

    def test_get_list_value_single_value(self, sample_gcode: Path):
        """_get_list_value with single non-list value should return list."""
        analyzer = GcodeAnalyzer(sample_gcode)
        analyzer.analyze()

        # layer_height is a single value "0.16"
        values = analyzer._get_list_value('layer_height')
        assert values == ['0.16']

    def test_get_value_with_both_separators(self, temp_dir: Path):
        """_get_value with value containing both ; and , should prefer ;."""
        gcode_path = temp_dir / "both_sep.gcode"
        gcode_path.write_text("""; CONFIG_BLOCK_START
; mixed_value = a,b;c,d
; CONFIG_BLOCK_END
""", encoding='utf-8')
        analyzer = GcodeAnalyzer(gcode_path)
        analyzer.analyze()

        # Semicolon takes priority over comma
        value = analyzer._get_value('mixed_value')
        assert value == 'a,b'

    def test_get_list_value_missing_key(self, sample_gcode: Path):
        """_get_list_value with missing key should return default."""
        analyzer = GcodeAnalyzer(sample_gcode)
        analyzer.analyze()

        values = analyzer._get_list_value('nonexistent_key', ['default'])
        assert values == ['default']

    def test_get_list_value_missing_key_no_default(self, sample_gcode: Path):
        """_get_list_value with missing key and no default should return empty list."""
        analyzer = GcodeAnalyzer(sample_gcode)
        analyzer.analyze()

        values = analyzer._get_list_value('nonexistent_key')
        assert values == []


# ═══════════════════════════════════════════════════════════════
# Test GcodeCustomGlobalSettings (dedicated)
# ═══════════════════════════════════════════════════════════════

class TestGcodeCustomGlobalSettings:
    """Dedicated tests for GcodeAnalyzer._get_custom_global_settings."""

    def test_extracts_custom_settings(self, sample_gcode: Path):
        """Should extract settings listed in different_settings_to_system."""
        analyzer = GcodeAnalyzer(sample_gcode)
        analyzer.analyze()

        custom = analyzer._get_custom_global_settings()
        assert 'wall_loops' in custom
        assert custom['wall_loops'] == '3'
        assert 'sparse_infill_density' in custom
        assert custom['sparse_infill_density'] == '15%'

    def test_empty_different_settings(self, temp_dir: Path):
        """Empty different_settings_to_system should return empty dict."""
        gcode_path = temp_dir / "empty_diff.gcode"
        gcode_path.write_text("""; CONFIG_BLOCK_START
; different_settings_to_system = 
; CONFIG_BLOCK_END
""", encoding='utf-8')
        analyzer = GcodeAnalyzer(gcode_path)
        analyzer.analyze()

        custom = analyzer._get_custom_global_settings()
        assert custom == {}

    def test_missing_different_settings(self, temp_dir: Path):
        """Missing different_settings_to_system should return empty dict."""
        gcode_path = temp_dir / "no_diff.gcode"
        gcode_path.write_text("""; CONFIG_BLOCK_START
; layer_height = 0.2
; CONFIG_BLOCK_END
""", encoding='utf-8')
        analyzer = GcodeAnalyzer(gcode_path)
        analyzer.analyze()

        custom = analyzer._get_custom_global_settings()
        assert custom == {}

    def test_key_listed_but_not_in_settings(self, temp_dir: Path):
        """Key in different_settings but not in settings should be skipped."""
        gcode_path = temp_dir / "missing_key.gcode"
        gcode_path.write_text("""; CONFIG_BLOCK_START
; different_settings_to_system = ghost_key;layer_height
; layer_height = 0.2
; CONFIG_BLOCK_END
""", encoding='utf-8')
        analyzer = GcodeAnalyzer(gcode_path)
        analyzer.analyze()

        custom = analyzer._get_custom_global_settings()
        assert 'ghost_key' not in custom
        assert 'layer_height' in custom
        assert custom['layer_height'] == '0.2'


# ═══════════════════════════════════════════════════════════════
# Test Edge Cases for Gcode Parsing
# ═══════════════════════════════════════════════════════════════

class TestGcodeEdgeCases:
    """Edge case tests for gcode parsing."""

    def test_malformed_generated_by_header(self, temp_dir: Path):
        """Malformed 'generated by' line should not crash."""
        gcode_path = temp_dir / "bad_header.gcode"
        gcode_path.write_text("""; HEADER_BLOCK_START
; generated by SomeSlicer without version info
; HEADER_BLOCK_END

; CONFIG_BLOCK_START
; layer_height = 0.2
; CONFIG_BLOCK_END
""", encoding='utf-8')
        analyzer = GcodeAnalyzer(gcode_path)
        result = analyzer.analyze()

        # Should not crash; slicer info may be empty
        assert result['statistics']['slicer'] == ''

    def test_config_value_containing_equals(self, temp_dir: Path):
        """Config value containing '=' should parse correctly."""
        gcode_path = temp_dir / "equals_value.gcode"
        gcode_path.write_text("""; CONFIG_BLOCK_START
; some_key = val = extra
; layer_height = 0.2
; CONFIG_BLOCK_END
""", encoding='utf-8')
        analyzer = GcodeAnalyzer(gcode_path)
        analyzer.analyze()

        # partition(' = ') splits on the first occurrence only
        assert analyzer.settings.get('some_key') == 'val = extra'
        assert analyzer.settings.get('layer_height') == '0.2'

    def test_non_numeric_statistics_values(self, temp_dir: Path):
        """Non-numeric statistics should not crash the parser."""
        gcode_path = temp_dir / "bad_stats.gcode"
        gcode_path.write_text("""; HEADER_BLOCK_START
; total layer number: not_a_number
; max_z_height: also_not_a_number
; HEADER_BLOCK_END

; CONFIG_BLOCK_START
; layer_height = 0.2
; CONFIG_BLOCK_END
""", encoding='utf-8')
        analyzer = GcodeAnalyzer(gcode_path)
        result = analyzer.analyze()

        # Bug fix 1c ensures these fallback to 0
        assert result['statistics']['total_layers'] == 0
        assert result['statistics']['max_height'] == 0.0

    def test_build_statistics_with_new_fields(self, sample_gcode: Path):
        """_build_statistics should include all new fields."""
        analyzer = GcodeAnalyzer(sample_gcode)
        result = analyzer.analyze()

        stats = result['statistics']
        assert 'printer_model' in stats
        assert stats['printer_model'] == 'Snapmaker U1'
        assert 'gcode_flavor' in stats
        assert stats['gcode_flavor'] == 'marlin'
        assert 'nozzle_type' in stats
        assert stats['nozzle_type'] == 'hardened_steel'
        assert 'curr_bed_type' in stats
        assert stats['curr_bed_type'] == 'Engineering Plate'
        assert 'filament_vendor' in stats
        assert 'Snapmaker' in stats['filament_vendor']
        assert 'eSUN' in stats['filament_vendor']
        assert 'enable_prime_tower' in stats
        assert stats['enable_prime_tower'] == '0'
        assert 'filament_used_per_extruder_cm3' in stats

    def test_build_statistics_fallback_paths(self, temp_dir: Path):
        """_build_statistics should handle missing optional fields."""
        gcode_path = temp_dir / "minimal_stats.gcode"
        gcode_path.write_text("""; CONFIG_BLOCK_START
; layer_height = 0.2
; CONFIG_BLOCK_END
""", encoding='utf-8')
        analyzer = GcodeAnalyzer(gcode_path)
        result = analyzer.analyze()

        stats = result['statistics']
        assert stats['printer_model'] == ''
        assert stats['gcode_flavor'] == ''
        assert stats['nozzle_type'] == ''
        assert stats['curr_bed_type'] == ''
        assert stats['filament_vendor'] == []
        assert stats['enable_prime_tower'] == ''
        assert stats['filament_used_per_extruder_cm3'] == []
        assert stats['filament_cost_per_extruder'] == []
        assert stats['total_layers'] == 0
        assert stats['max_height'] == 0.0


# ═══════════════════════════════════════════════════════════════
# Test CLI combined flags for gcode
# ═══════════════════════════════════════════════════════════════

class TestGcodeCLICombinedFlags:
    """Test combined CLI flags for gcode files."""

    def test_main_gcode_combined_flags(self, sample_gcode: Path, capsys):
        """Multiple flags should work together for gcode files."""
        with patch.object(sys, 'argv', ['analyze.py', str(sample_gcode), '--diff', '--wiki', '--no-color']):
            main()

        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_main_gcode_json_verbose(self, sample_gcode: Path, capsys):
        """--json and --verbose should work together for gcode."""
        with patch.object(sys, 'argv', ['analyze.py', str(sample_gcode), '--json', '--verbose']):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert 'statistics' in data
        assert 'printer_model' in data['statistics']
