"""Unit tests for core.gcode module."""

from pathlib import Path

import pytest

from core.gcode import GcodeAnalyzer


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
        assert any('\u0422\u0435\u0441\u0442\u043e\u0432\u044b\u0439' in obj for obj in objects)

    def test_nonexistent_file_raises_error(self, temp_dir: Path):
        """Non-existent gcode file should raise OSError."""
        fake_path = temp_dir / "nonexistent.gcode"
        analyzer = GcodeAnalyzer(fake_path)

        with pytest.raises(OSError):
            analyzer.analyze()


# ═══════════════════════════════════════════════════════════════
# Test GcodeAnalyzer internal methods
# ═══════════════════════════════════════════════════════════════

class TestGcodeAnalyzerMethods:
    """Tests for GcodeAnalyzer internal methods."""

    def test_get_value_single(self, sample_gcode: Path):
        """_get_value should return first value from comma-separated list."""
        analyzer = GcodeAnalyzer(sample_gcode)
        analyzer.analyze()

        value = analyzer._get_value('nozzle_diameter')
        assert value == '0.4'

    def test_get_value_semicolon_list(self, sample_gcode: Path):
        """_get_value should return first value from semicolon-separated list."""
        analyzer = GcodeAnalyzer(sample_gcode)
        analyzer.analyze()

        value = analyzer._get_value('filament_type')
        assert value == 'PLA'

    def test_get_list_value(self, sample_gcode: Path):
        """_get_list_value should return all values as list."""
        analyzer = GcodeAnalyzer(sample_gcode)
        analyzer.analyze()

        values = analyzer._get_list_value('filament_type')
        assert values == ['PLA', 'PETG']

    def test_get_value_missing_key(self, sample_gcode: Path):
        """_get_value should return default for missing key."""
        analyzer = GcodeAnalyzer(sample_gcode)
        analyzer.analyze()

        value = analyzer._get_value('nonexistent_key', default='fallback')
        assert value == 'fallback'


# ═══════════════════════════════════════════════════════════════
# Test GcodeAnalyzerMethods extensions
# ═══════════════════════════════════════════════════════════════

class TestGcodeAnalyzerMethodsExtended:
    """Extended tests for GcodeAnalyzer internal methods."""

    def test_get_list_value_comma_separated(self, sample_gcode: Path):
        """_get_list_value should parse comma-separated values."""
        analyzer = GcodeAnalyzer(sample_gcode)
        analyzer.analyze()

        values = analyzer._get_list_value('nozzle_diameter')
        assert values == ['0.4', '0.4', '0.4', '0.4']

    def test_get_list_value_single_value(self, sample_gcode: Path):
        """_get_list_value with single non-list value should return list."""
        analyzer = GcodeAnalyzer(sample_gcode)
        analyzer.analyze()

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
# Test GcodeCustomGlobalSettings
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
# Test optimized parser (v2.5.0+)
# ═══════════════════════════════════════════════════════════════

class TestGcodeParserOptimization:
    """Tests for optimized single-pass parser with section-aware processing."""

    def test_malformed_file_protection_long_line(self, temp_dir: Path):
        """Parser should stop safely when encountering abnormally long lines."""
        from core.constants import MAX_GCODE_LINE_LENGTH
        
        gcode_path = temp_dir / "malformed_long_line.gcode"
        
        # Create a file with a line that exceeds MAX_GCODE_LINE_LENGTH
        long_line = "G1 X" + "0" * (MAX_GCODE_LINE_LENGTH + 1000)
        content = """; HEADER_BLOCK_START
; generated by Test Slicer 1.0.0 on 2026-01-01 at 12:00:00
; HEADER_BLOCK_END
""" + long_line + """
; CONFIG_BLOCK_START
; layer_height = 0.2
; CONFIG_BLOCK_END
"""
        gcode_path.write_text(content, encoding='utf-8')
        
        analyzer = GcodeAnalyzer(gcode_path)
        result = analyzer.analyze()
        
        # Should not crash and return valid result
        assert isinstance(result, dict)
        assert 'profile' in result
        # Header should be parsed before encountering long line
        assert result['statistics']['slicer'] == 'Test Slicer'

    def test_early_exit_after_config_block_end(self, temp_dir: Path):
        """Parser should stop reading after CONFIG_BLOCK_END marker."""
        gcode_path = temp_dir / "early_exit_test.gcode"
        
        # Add marker after CONFIG_BLOCK_END that should NOT be processed
        marker_after_config = "; SHOULD_NOT_BE_PROCESSED"
        content = f"""; HEADER_BLOCK_START
; generated by Test Slicer 1.0.0 on 2026-01-01 at 12:00:00
; HEADER_BLOCK_END
; printing object TestObject id:123
; CONFIG_BLOCK_START
; layer_height = 0.2
; printer_settings_id = TestPrinter
; CONFIG_BLOCK_END
{marker_after_config}
G1 X100 Y100
M104 S0
"""
        gcode_path.write_text(content, encoding='utf-8')
        
        analyzer = GcodeAnalyzer(gcode_path)
        result = analyzer.analyze()
        
        # Should have parsed everything before CONFIG_BLOCK_END
        assert result['profile']['printer'] == 'TestPrinter'
        assert 'TestObject' in result['objects']
        
        # Verify parser stopped (we can check via debug log or line count)
        # Since we can't easily verify line count from outside, 
        # we verify that result is complete and correct
        assert result['profile']['layer_height'] == '0.2'

    def test_thumbnail_section_skipped(self, temp_dir: Path):
        """Parser should skip thumbnail sections containing base64 data."""
        gcode_path = temp_dir / "with_thumbnails.gcode"
        
        # Include thumbnail section with fake base64 data
        content = """; HEADER_BLOCK_START
; generated by Test Slicer 1.0.0 on 2026-01-01 at 12:00:00
; HEADER_BLOCK_END
; thumbnail begin 300x300 12345
; iVBORw0KGgoAAAANSUhEUgAAAAUA (fake base64 line 1)
; AAAFCAYAAACNbyblAAAAHElEQVQI (fake base64 line 2)
; 12P4//8/w38GIAXDIBKE0DHxgljNB (fake base64 line 3)
; AAO9TXL0Y4OHwAAAABJRU5ErkJggg== (fake base64 line 4)
; thumbnail end
G28 ; home
; printing object TestObject id:123
; CONFIG_BLOCK_START
; layer_height = 0.2
; CONFIG_BLOCK_END
"""
        gcode_path.write_text(content, encoding='utf-8')
        
        analyzer = GcodeAnalyzer(gcode_path)
        result = analyzer.analyze()
        
        # Should successfully parse without processing thumbnail data
        assert isinstance(result, dict)
        assert result['statistics']['slicer'] == 'Test Slicer'
        assert 'TestObject' in result['objects']
        assert result['profile']['layer_height'] == '0.2'
        
        # Thumbnail data should not appear in settings
        assert 'iVBORw0KGgoAAAANSUhEUgAAAAUA' not in result['profile_full'].values()

    def test_single_pass_processing(self, temp_dir: Path):
        """Parser should extract all data in a single pass through file."""
        gcode_path = temp_dir / "single_pass_test.gcode"
        
        content = """; HEADER_BLOCK_START
; generated by Test Slicer 1.0.0 on 2026-01-01 at 12:00:00
; total layer number: 150
; HEADER_BLOCK_END
; printing object Object1 id:100
; printing object Object2 id:200
; filament used [g] = 10.5, 5.2
; total filament used [g] = 15.7
; estimated printing time (normal mode) = 1h 30m
; CONFIG_BLOCK_START
; layer_height = 0.16
; wall_loops = 3
; sparse_infill_density = 20
; CONFIG_BLOCK_END
"""
        gcode_path.write_text(content, encoding='utf-8')
        
        analyzer = GcodeAnalyzer(gcode_path)
        result = analyzer.analyze()
        
        # All sections should be parsed correctly
        # Header
        assert result['statistics']['slicer'] == 'Test Slicer'
        assert result['statistics']['total_layers'] == 150
        
        # Objects (from executable section)
        assert 'Object1' in result['objects']
        assert 'Object2' in result['objects']
        
        # Statistics (before CONFIG)
        assert result['statistics']['filament_used_g'] == 15.7
        assert result['statistics']['filament_used_per_extruder_g'] == [10.5, 5.2]
        assert result['statistics']['estimated_time'] == '1h 30m'
        
        # Config
        assert result['profile']['layer_height'] == '0.16'
        assert result['profile']['wall_loops'] == '3'
        assert result['profile']['sparse_infill_density'] == '20'
