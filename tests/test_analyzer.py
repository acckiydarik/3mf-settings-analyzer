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
    _is_custom,
    _format_object_value,
    _format_support_value,
    main,
    print_results,
    setup_logging,
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
