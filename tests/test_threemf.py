"""Unit tests for core.threemf module."""

import json
import logging
import zipfile
from pathlib import Path
from xml.etree.ElementTree import ParseError

import pytest

from core.threemf import ThreeMFAnalyzer, _is_custom


# ═══════════════════════════════════════════════════════════════
# Test _is_custom helper function
# ═══════════════════════════════════════════════════════════════

class TestIsCustom:
    """Tests for the _is_custom helper function."""

    @pytest.mark.parametrize("obj_val, global_val, expected", [
        (None, "any_value", False),
        ("10", "10", False),
        (10, 10, False),
        ("0.2", "0.2", False),
        ("15", "10", True),
        ("0.3", "0.2", True),
        (10, "10", False),
        ("10", 10, False),
        ("", "default", True),
    ])
    def test_is_custom(self, obj_val, global_val, expected):
        assert _is_custom(obj_val, global_val) is expected


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
        analyzer.analyze()

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
        analyzer.analyze()

        assert analyzer._get_value('layer_height') == '0.2'

    def test_get_list_value_first_element(self, sample_3mf: Path):
        """Should return first element of list by default."""
        analyzer = ThreeMFAnalyzer(sample_3mf)
        analyzer.analyze()

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
# Test format functions (ThreeMFAnalyzer instance methods)
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
# Test Multi-Plate Support
# ═══════════════════════════════════════════════════════════════

class TestMultiPlateSupport:
    """Tests for 3MF files with multiple plates."""

    def test_multi_plate_extraction(self, multi_plate_3mf: Path):
        """Analyzer should extract objects from multiple plates."""
        analyzer = ThreeMFAnalyzer(multi_plate_3mf)
        result = analyzer.analyze()

        rows = result['rows']
        assert len(rows) == 3

        names = [r['name'] for r in rows]
        assert 'Object_Plate1' in names
        assert 'Object_Plate2_First' in names
        assert 'Object_Plate2_Second' in names

    def test_multi_plate_order(self, multi_plate_3mf: Path):
        """Objects should be ordered by plate and identify_id."""
        analyzer = ThreeMFAnalyzer(multi_plate_3mf)
        analyzer.analyze()

        assert len(analyzer.plates) == 2
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
        assert len(rows) >= 3

        names = [r['name'].strip() for r in rows]
        assert 'PartA' in names
        assert 'PartB' in names
        assert 'PartC' in names

    def test_part_custom_settings(self, multi_part_object_3mf: Path):
        """Parts should have their own custom settings."""
        analyzer = ThreeMFAnalyzer(multi_part_object_3mf)
        result = analyzer.analyze()

        rows = result['rows']
        part_a = next((r for r in rows if r['name'].strip() == 'PartA'), None)
        part_b = next((r for r in rows if r['name'].strip() == 'PartB'), None)

        assert part_a is not None
        assert part_b is not None

        assert '30' in part_a['infill']
        assert '50' in part_b['infill']

    def test_part_extruder_assignment(self, multi_part_object_3mf: Path):
        """Parts can have different extruder assignments."""
        analyzer = ThreeMFAnalyzer(multi_part_object_3mf)
        result = analyzer.analyze()

        rows = result['rows']
        part_a = next((r for r in rows if r['name'].strip() == 'PartA'), None)
        part_b = next((r for r in rows if r['name'].strip() == 'PartB'), None)

        assert part_a is not None
        assert part_b is not None
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

        obj = next((r for r in rows if 'Тестовый' in r['name']), None)
        assert obj is not None
        assert '测试' in obj['name']

    def test_unicode_part_name(self, unicode_names_3mf: Path):
        """Analyzer should handle Unicode part names."""
        analyzer = ThreeMFAnalyzer(unicode_names_3mf)
        result = analyzer.analyze()

        rows = result['rows']
        part = next((r for r in rows if r.get('part_id') is not None and 'Часть' in r['name'].strip()), None)
        if part is None:
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

        assert result['profile']['filaments'] == []

    def test_get_value_empty_list_with_index(self, empty_list_settings_3mf: Path):
        """_get_value should return default for empty list with index > 0."""
        analyzer = ThreeMFAnalyzer(empty_list_settings_3mf)
        analyzer.analyze()

        value = analyzer._get_value('filament_settings_id', default='fallback', index=0)
        assert value == 'fallback'

        value = analyzer._get_value('filament_settings_id', default='fallback', index=5)
        assert value == 'fallback'

    def test_non_3mf_extension_warning(self, temp_dir: Path, sample_project_settings: dict, sample_model_settings_xml: str, caplog):
        """File without .3mf extension should still work but may log warning."""
        wrong_ext = temp_dir / "test_file.zip"
        with zipfile.ZipFile(wrong_ext, 'w') as zf:
            zf.writestr("Metadata/project_settings.config", json.dumps(sample_project_settings))
            zf.writestr("Metadata/model_settings.config", sample_model_settings_xml)

        analyzer = ThreeMFAnalyzer(wrong_ext)

        with caplog.at_level(logging.DEBUG):
            result = analyzer.analyze()

        assert result['profile']['printer'] == "Bambu Lab A1 mini 0.4 nozzle"
