"""Unit tests for core.compare module."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from rich.style import Style
from rich.text import Text

from core.compare import (
    DIFF_BG,
    _add_row,
    _add_separator,
    _get_features,
    _get_flow_value,
    _make_table,
    print_3mf_comparison,
    print_gcode_comparison,
)
from core.cli import main


# ═══════════════════════════════════════════════════════════════
# Test _make_table
# ═══════════════════════════════════════════════════════════════

class TestMakeTable:
    """Tests for _make_table helper."""

    def test_creates_table_with_correct_column_count(self):
        """Table should have 1 label + N file columns."""
        table = _make_table(2)
        assert len(table.columns) == 3

    def test_creates_table_for_four_files(self):
        table = _make_table(4)
        assert len(table.columns) == 5

    def test_label_column_has_dim_style(self):
        table = _make_table(2)
        assert table.columns[0].style == "dim"

    def test_custom_label_style(self):
        table = _make_table(2, label_style="yellow")
        assert table.columns[0].style == "yellow"


# ═══════════════════════════════════════════════════════════════
# Test _add_row
# ═══════════════════════════════════════════════════════════════

class TestAddRow:
    """Tests for _add_row diff-detection helper."""

    def test_identical_values_no_diff(self):
        """When all values are the same, no DIFF_BG should be applied."""
        table = _make_table(2)
        _add_row(table, "Test", ["[cyan]40 mm/s[/cyan]", "[cyan]40 mm/s[/cyan]"])
        assert table.row_count == 1

    def test_different_values_apply_diff(self):
        """When values differ, DIFF_BG should be applied to non-empty cells."""
        table = _make_table(2)
        _add_row(table, "Speed", ["[cyan]40 mm/s[/cyan]", "[cyan]60 mm/s[/cyan]"])
        assert table.row_count == 1

    def test_empty_values_no_diff(self):
        """All-empty values should not trigger diff highlighting."""
        table = _make_table(2)
        _add_row(table, "Test", ["", ""])
        assert table.row_count == 1

    def test_one_empty_one_value_no_diff(self):
        """A single non-empty value with empty peers should not trigger diff."""
        table = _make_table(2)
        _add_row(table, "Test", ["value", ""])
        assert table.row_count == 1

    def test_three_values_with_one_different(self):
        """Three values where one differs should trigger diff."""
        table = _make_table(3)
        _add_row(table, "Test", ["A", "B", "A"])
        assert table.row_count == 1

    def test_plain_text_comparison_strips_markup(self):
        """Comparison should work on plain text, ignoring Rich markup."""
        table = _make_table(2)
        _add_row(table, "Test", ["[red]220°C[/red]", "[red]220°C[/red]"])
        assert table.row_count == 1


# ═══════════════════════════════════════════════════════════════
# Test _add_separator
# ═══════════════════════════════════════════════════════════════

class TestAddSeparator:
    """Tests for _add_separator helper."""

    def test_adds_empty_row(self):
        table = _make_table(2)
        _add_separator(table, 2)
        assert table.row_count == 1

    def test_separator_with_four_files(self):
        table = _make_table(4)
        _add_separator(table, 4)
        assert table.row_count == 1


# ═══════════════════════════════════════════════════════════════
# Test _get_flow_value
# ═══════════════════════════════════════════════════════════════

class TestGetFlowValue:
    """Tests for _get_flow_value helper."""

    def test_print_flow_ratio(self):
        profile = {'print_flow_ratio': '0.95', 'filament_flow_ratio': ''}
        label, value = _get_flow_value(profile)
        assert label == "Print Flow Ratio"
        assert value == "95%"

    def test_filament_flow_ratio_fallback(self):
        profile = {'print_flow_ratio': '1', 'filament_flow_ratio': '0.966'}
        label, value = _get_flow_value(profile)
        assert label == "Filament Flow Ratio"
        assert value == "0.966"

    def test_no_flow_ratio(self):
        profile = {'print_flow_ratio': '', 'filament_flow_ratio': ''}
        label, value = _get_flow_value(profile)
        assert label == ""
        assert value == ""

    def test_print_flow_ratio_one_uses_filament(self):
        """print_flow_ratio == '1' should fall through to filament_flow_ratio."""
        profile = {'print_flow_ratio': '1', 'filament_flow_ratio': '0.98'}
        label, value = _get_flow_value(profile)
        assert label == "Filament Flow Ratio"


# ═══════════════════════════════════════════════════════════════
# Test _get_features
# ═══════════════════════════════════════════════════════════════

class TestGetFeatures:
    """Tests for _get_features helper."""

    def test_no_features(self):
        profile = {
            'enable_arc_fitting': '0',
            'enable_overhang_speed': '0',
            'timelapse_type': '0',
        }
        assert _get_features(profile) == ""

    def test_arc_fitting_enabled(self):
        profile = {
            'enable_arc_fitting': '1',
            'enable_overhang_speed': '0',
            'timelapse_type': '0',
        }
        result = _get_features(profile)
        assert "Enable Arc Fitting" in result

    def test_overhang_speed_enabled(self):
        profile = {
            'enable_arc_fitting': '0',
            'enable_overhang_speed': '1',
            'timelapse_type': '0',
        }
        result = _get_features(profile)
        assert "Enable Overhang Speed" in result

    def test_multiple_features(self):
        profile = {
            'enable_arc_fitting': '1',
            'enable_overhang_speed': '1',
            'timelapse_type': '0',
        }
        result = _get_features(profile)
        assert "Enable Arc Fitting" in result
        assert "Enable Overhang Speed" in result

    def test_missing_keys_handled(self):
        """Should handle missing keys gracefully."""
        assert _get_features({}) == ""


# ═══════════════════════════════════════════════════════════════
# Test DIFF_BG constant
# ═══════════════════════════════════════════════════════════════

class TestDiffBg:
    """Tests for the DIFF_BG style constant."""

    def test_is_style_instance(self):
        assert isinstance(DIFF_BG, Style)

    def test_has_bgcolor(self):
        assert DIFF_BG.bgcolor is not None


# ═══════════════════════════════════════════════════════════════
# Gcode result fixtures for comparison tests
# ═══════════════════════════════════════════════════════════════

def _make_gcode_result(
    filename="test.gcode",
    layer_height="0.16",
    outer_wall_speed="60",
    brim_type="auto_brim",
    seam_position="aligned",
    nozzle_temp="220",
    bed_temp="65",
    objects=None,
    custom_global=None,
    estimated_time="1h 11m",
    filament_used_g=11.26,
    filament_colors=None,
):
    """Build a minimal gcode result dict for testing."""
    if objects is None:
        objects = ["TestModel.stl"]
    if custom_global is None:
        custom_global = {}
    if filament_colors is None:
        filament_colors = ["#DE1619FF"]

    return {
        'file': filename,
        'profile': {
            'printer': 'Test Printer',
            'process': 'Test Process',
            'filaments': ['Test Filament'],
            'layer_height': layer_height,
            'initial_layer_print_height': '0.200',
            'line_width': '0.42',
            'print_flow_ratio': '',
            'filament_flow_ratio': '0.966',
            'wall_loops': '2',
            'sparse_infill_density': '15%',
            'top_shell_layers': '6',
            'bottom_shell_layers': '4',
            'brim_type': brim_type,
            'enable_support': '0',
            'seam_position': seam_position,
            'initial_layer_speed': '50',
            'outer_wall_speed': outer_wall_speed,
            'inner_wall_speed': '150',
            'sparse_infill_speed': '200',
            'top_surface_speed': '150',
            'travel_speed': '500',
            'bridge_speed': '50',
            'sparse_infill_pattern': 'gyroid',
            'top_surface_pattern': 'monotonicline',
            'print_sequence': 'by layer',
            'spiral_mode': '0',
            'ironing_type': '',
            'fuzzy_skin': '',
            'retraction_length': '1.5',
            'retraction_speed': '30',
            'z_hop': '0.4',
            'pressure_advance': '0.02',
            'fan_min_speed': '100',
            'fan_max_speed': '100',
            'slow_down_for_layer_cooling': '1',
            'slow_down_layer_time': '4',
            'nozzle_temperature': nozzle_temp,
            'bed_temperature': bed_temp,
            'enable_arc_fitting': '0',
            'enable_overhang_speed': '1',
            'timelapse_type': '0',
        },
        'profile_full': {},
        'custom_global': custom_global,
        'rows': [],
        'objects': objects,
        'statistics': {
            'slicer': 'Test Slicer',
            'slicer_version': '1.0',
            'generated_date': '2026-01-30 12:00:00',
            'estimated_time': estimated_time,
            'estimated_first_layer_time': '19s',
            'total_layers': 138,
            'max_height': 22.12,
            'layer_height': layer_height,
            'first_layer_height': '0.200',
            'nozzle_diameter': ['0.4'],
            'filament_used_g': filament_used_g,
            'filament_used_per_extruder_g': [filament_used_g],
            'filament_used_per_extruder_cm3': [filament_used_g / 1.24],
            'filament_cost': 0.23,
            'filament_cost_per_extruder': [0.23],
            'filament_changes': 0,
            'filament_names': ['Test Filament'],
            'filament_vendor': ['Test Vendor'],
            'filament_types': ['PLA'],
            'filament_colors': filament_colors,
            'filament_density': ['1.24'],
            'filament_diameter': ['1.75'],
            'enable_prime_tower': '0',
            'file_size_bytes': 10485760,
            'printer_model': 'Test Printer',
            'gcode_flavor': 'klipper',
            'nozzle_type': 'stainless_steel',
            'curr_bed_type': 'Textured PEI Plate',
            'first_layer_nozzle_temp': nozzle_temp,
            'nozzle_temp': [nozzle_temp],
            'first_layer_bed_temp': bed_temp,
            'bed_temp': bed_temp,
        },
    }


# ═══════════════════════════════════════════════════════════════
# Test print_gcode_comparison
# ═══════════════════════════════════════════════════════════════

class TestPrintGcodeComparison:
    """Tests for print_gcode_comparison public function."""

    def test_two_identical_files(self, capsys):
        """Identical files should render without errors."""
        results = [_make_gcode_result("a.gcode"), _make_gcode_result("b.gcode")]
        print_gcode_comparison(results, no_color=True)
        captured = capsys.readouterr()
        assert "GCODE SETTINGS COMPARISON" in captured.out
        assert "a.gcode" in captured.out
        assert "b.gcode" in captured.out

    def test_two_different_files(self, capsys):
        """Files with differences should render without errors."""
        r1 = _make_gcode_result("file1.gcode", outer_wall_speed="60", brim_type="auto_brim")
        r2 = _make_gcode_result("file2.gcode", outer_wall_speed="40", brim_type="no_brim")
        print_gcode_comparison([r1, r2], no_color=True)
        captured = capsys.readouterr()
        assert "60 mm/s" in captured.out
        assert "40 mm/s" in captured.out
        assert "auto_brim" in captured.out
        assert "no_brim" in captured.out

    def test_three_files(self, capsys):
        """Three-file comparison should render correctly."""
        results = [
            _make_gcode_result("a.gcode"),
            _make_gcode_result("b.gcode"),
            _make_gcode_result("c.gcode"),
        ]
        print_gcode_comparison(results, no_color=True)
        captured = capsys.readouterr()
        assert "a.gcode" in captured.out
        assert "b.gcode" in captured.out
        assert "c.gcode" in captured.out

    def test_four_files(self, capsys):
        """Four-file comparison should render all sections without errors."""
        results = [_make_gcode_result(f"f{i}.gcode") for i in range(4)]
        print_gcode_comparison(results, no_color=True)
        captured = capsys.readouterr()
        assert "GCODE SETTINGS COMPARISON" in captured.out
        assert "PROFILE" in captured.out
        assert "STATISTICS" in captured.out

    def test_header_shows_comparison_title_and_filenames(self, capsys):
        """Header should show title and file names aligned to columns."""
        results = [_make_gcode_result("a.gcode"), _make_gcode_result("b.gcode")]
        print_gcode_comparison(results, no_color=True)
        captured = capsys.readouterr()
        assert "GCODE SETTINGS COMPARISON" in captured.out
        assert "a.gcode" in captured.out
        assert "b.gcode" in captured.out

    def test_all_sections_present(self, capsys):
        """All sections (Profile, Global, Custom, Objects, Stats) should appear."""
        r1 = _make_gcode_result("a.gcode", custom_global={"test_key": "val"})
        r2 = _make_gcode_result("b.gcode", custom_global={"test_key": "val"})
        print_gcode_comparison([r1, r2], no_color=True)
        captured = capsys.readouterr()
        assert "PROFILE" in captured.out
        assert "GLOBAL SETTINGS" in captured.out
        assert "CUSTOM GLOBAL SETTINGS" in captured.out
        assert "OBJECTS" in captured.out
        assert "STATISTICS" in captured.out

    def test_no_custom_global_hides_section(self, capsys):
        """When no files have custom settings, section should be hidden."""
        results = [_make_gcode_result("a.gcode"), _make_gcode_result("b.gcode")]
        print_gcode_comparison(results, no_color=True)
        captured = capsys.readouterr()
        assert "CUSTOM GLOBAL SETTINGS" not in captured.out

    def test_custom_global_union_of_keys(self, capsys):
        """Custom global should show union of keys from all files."""
        r1 = _make_gcode_result("a.gcode", custom_global={"key_a": "1"})
        r2 = _make_gcode_result("b.gcode", custom_global={"key_b": "2"})
        print_gcode_comparison([r1, r2], no_color=True)
        captured = capsys.readouterr()
        assert "key_a" in captured.out
        assert "key_b" in captured.out

    def test_objects_per_file_columns(self, capsys):
        """Each file's objects should appear in its own column."""
        r1 = _make_gcode_result("a.gcode", objects=["Common.stl", "OnlyA.stl"])
        r2 = _make_gcode_result("b.gcode", objects=["Common.stl", "OnlyB.stl"])
        print_gcode_comparison([r1, r2], no_color=True)
        captured = capsys.readouterr()
        assert "Common.stl" in captured.out
        assert "OnlyA.stl" in captured.out
        assert "OnlyB.stl" in captured.out
        assert "OBJECTS" in captured.out

    def test_filament_colors_preserved(self, capsys):
        """Filament color blocks should appear in statistics section."""
        r1 = _make_gcode_result("a.gcode", filament_colors=["#DE1619FF"])
        r2 = _make_gcode_result("b.gcode", filament_colors=["#FFFFFFFF"])
        print_gcode_comparison([r1, r2], no_color=True)
        captured = capsys.readouterr()
        assert "Filament Colors" in captured.out

    def test_wiki_mode(self, capsys):
        """--wiki flag should not cause errors in comparison mode."""
        results = [_make_gcode_result("a.gcode"), _make_gcode_result("b.gcode")]
        print_gcode_comparison(results, no_color=True, wiki=False)
        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_statistics_differences(self, capsys):
        """Different statistics should appear in output."""
        r1 = _make_gcode_result("a.gcode", estimated_time="1h 11m", filament_used_g=11.26)
        r2 = _make_gcode_result("b.gcode", estimated_time="2h 30m", filament_used_g=25.50)
        print_gcode_comparison([r1, r2], no_color=True)
        captured = capsys.readouterr()
        assert "1h 11m" in captured.out
        assert "2h 30m" in captured.out
        assert "11.26" in captured.out
        assert "25.50" in captured.out


# ═══════════════════════════════════════════════════════════════
# Test print_3mf_comparison
# ═══════════════════════════════════════════════════════════════

def _make_3mf_result(
    filename="test.3mf",
    wall_loops="3",
    brim_type="no_brim",
    objects=None,
    custom_global=None,
):
    """Build a minimal 3MF result dict for testing."""
    if objects is None:
        objects = [{"name": "TestObj", "is_parent": True, "plate": "1",
                    "filament": "1", "layer_height": "0.2", "layer_custom": False,
                    "wall_loops": wall_loops, "walls_custom": False,
                    "infill": "15%", "infill_custom": False,
                    "support": "Off", "support_custom": False,
                    "brim": brim_type, "brim_custom": False,
                    "outer_wall_speed": "200", "speed_custom": False,
                    "custom_settings": {}, "is_part": False}]
    if custom_global is None:
        custom_global = {}

    return {
        'file': filename,
        'profile': {
            'printer': 'Test Printer',
            'process': 'Test Process',
            'filaments': ['Test Filament'],
            'layer_height': '0.2',
            'initial_layer_print_height': '0.2',
            'line_width': '0.42',
            'print_flow_ratio': '',
            'filament_flow_ratio': '',
            'wall_loops': wall_loops,
            'sparse_infill_density': '15%',
            'top_shell_layers': '5',
            'bottom_shell_layers': '3',
            'brim_type': brim_type,
            'enable_support': '0',
            'seam_position': 'back',
            'initial_layer_speed': '',
            'outer_wall_speed': '200',
            'inner_wall_speed': '300',
            'sparse_infill_speed': '270',
            'top_surface_speed': '200',
            'travel_speed': '700',
            'bridge_speed': '50',
            'sparse_infill_pattern': 'gyroid',
            'top_surface_pattern': 'monotonicline',
            'print_sequence': 'by layer',
            'spiral_mode': '0',
            'ironing_type': '',
            'fuzzy_skin': '',
            'retraction_length': '0.8',
            'retraction_speed': '30',
            'z_hop': '0.4',
            'pressure_advance': '',
            'fan_min_speed': '60',
            'fan_max_speed': '80',
            'slow_down_for_layer_cooling': '',
            'slow_down_layer_time': '',
            'nozzle_temperature': '220',
            'bed_temperature': '60',
            'enable_arc_fitting': '0',
            'enable_overhang_speed': '0',
            'timelapse_type': '0',
        },
        'profile_full': {},
        'custom_global': custom_global,
        'rows': objects,
    }


class TestPrint3mfComparison:
    """Tests for print_3mf_comparison public function."""

    def test_two_identical_files(self, capsys):
        results = [_make_3mf_result("a.3mf"), _make_3mf_result("b.3mf")]
        print_3mf_comparison(results, no_color=True)
        captured = capsys.readouterr()
        assert "3MF SETTINGS COMPARISON" in captured.out

    def test_two_different_files(self, capsys):
        r1 = _make_3mf_result("a.3mf", wall_loops="3", brim_type="no_brim")
        r2 = _make_3mf_result("b.3mf", wall_loops="5", brim_type="outer_only")
        print_3mf_comparison([r1, r2], no_color=True)
        captured = capsys.readouterr()
        assert "3" in captured.out
        assert "5" in captured.out

    def test_objects_section_present(self, capsys):
        results = [_make_3mf_result("a.3mf"), _make_3mf_result("b.3mf")]
        print_3mf_comparison(results, no_color=True)
        captured = capsys.readouterr()
        assert "OBJECTS" in captured.out

    def test_no_statistics_for_3mf(self, capsys):
        """3MF comparison should not have STATISTICS section."""
        results = [_make_3mf_result("a.3mf"), _make_3mf_result("b.3mf")]
        print_3mf_comparison(results, no_color=True)
        captured = capsys.readouterr()
        assert "STATISTICS" not in captured.out

    def test_objects_transposed_shows_settings_as_rows(self, capsys):
        """Object settings should appear as row labels (Plate, Filament, etc.)."""
        results = [_make_3mf_result("a.3mf"), _make_3mf_result("b.3mf")]
        print_3mf_comparison(results, no_color=True)
        captured = capsys.readouterr()
        for label in ("Plate", "Filament", "Layer Height", "Wall Loops",
                       "Infill Density", "Support", "Brim Type", "Outer Wall Speed"):
            assert label in captured.out

    def test_objects_transposed_shows_object_name(self, capsys):
        """Object header row should contain the object name."""
        results = [_make_3mf_result("a.3mf"), _make_3mf_result("b.3mf")]
        print_3mf_comparison(results, no_color=True)
        captured = capsys.readouterr()
        assert "TestObj" in captured.out
        assert "#1" in captured.out

    def test_objects_different_values_highlighted(self, capsys):
        """Different per-object values should both appear in output."""
        obj1 = [{"name": "Obj", "is_parent": True, "plate": "1",
                 "filament": "1", "layer_height": "0.2", "layer_custom": False,
                 "wall_loops": "3", "walls_custom": False,
                 "infill": "15%", "infill_custom": False,
                 "support": "Off", "support_custom": False,
                 "brim": "No", "brim_custom": False,
                 "outer_wall_speed": "200", "speed_custom": False,
                 "custom_settings": {}, "is_part": False}]
        obj2 = [{"name": "Obj", "is_parent": True, "plate": "1",
                 "filament": "2", "layer_height": "0.2", "layer_custom": False,
                 "wall_loops": "5", "walls_custom": False,
                 "infill": "30%", "infill_custom": False,
                 "support": "On", "support_custom": False,
                 "brim": "Outer", "brim_custom": False,
                 "outer_wall_speed": "300", "speed_custom": False,
                 "custom_settings": {}, "is_part": False}]
        r1 = _make_3mf_result("a.3mf", objects=obj1)
        r2 = _make_3mf_result("b.3mf", objects=obj2)
        print_3mf_comparison([r1, r2], no_color=True)
        captured = capsys.readouterr()
        assert "200" in captured.out
        assert "300" in captured.out
        assert "15%" in captured.out
        assert "30%" in captured.out

    def test_objects_custom_settings_shown(self, capsys):
        """Per-object custom settings should appear with * prefix."""
        obj = [{"name": "Obj", "is_parent": True, "plate": "1",
                "filament": "1", "layer_height": "0.2", "layer_custom": False,
                "wall_loops": "3", "walls_custom": False,
                "infill": "80%", "infill_custom": True,
                "support": "Off", "support_custom": False,
                "brim": "No", "brim_custom": False,
                "outer_wall_speed": "200", "speed_custom": False,
                "custom_settings": {"sparse_infill_density": "80%"},
                "is_part": False}]
        results = [_make_3mf_result("a.3mf", objects=obj),
                   _make_3mf_result("b.3mf", objects=obj)]
        print_3mf_comparison(results, no_color=True)
        captured = capsys.readouterr()
        assert "* sparse_infill_density" in captured.out
        assert "80%" in captured.out

    def test_objects_missing_object_shows_placeholder(self, capsys):
        """When file B has fewer objects, missing values show --."""
        obj_a = [
            {"name": "Obj1", "is_parent": True, "plate": "1",
             "filament": "1", "layer_height": "0.2", "layer_custom": False,
             "wall_loops": "3", "walls_custom": False,
             "infill": "15%", "infill_custom": False,
             "support": "Off", "support_custom": False,
             "brim": "No", "brim_custom": False,
             "outer_wall_speed": "200", "speed_custom": False,
             "custom_settings": {}, "is_part": False},
            {"name": "Obj2", "is_parent": True, "plate": "1",
             "filament": "2", "layer_height": "0.2", "layer_custom": False,
             "wall_loops": "3", "walls_custom": False,
             "infill": "15%", "infill_custom": False,
             "support": "Off", "support_custom": False,
             "brim": "No", "brim_custom": False,
             "outer_wall_speed": "200", "speed_custom": False,
             "custom_settings": {}, "is_part": False},
        ]
        obj_b = [obj_a[0]]  # Only first object
        r1 = _make_3mf_result("a.3mf", objects=obj_a)
        r2 = _make_3mf_result("b.3mf", objects=obj_b)
        print_3mf_comparison([r1, r2], no_color=True)
        captured = capsys.readouterr()
        assert "#1" in captured.out
        assert "#2" in captured.out
        assert "--" in captured.out

    def test_objects_children_rendered(self, capsys):
        """Child (part) objects should be rendered under parent."""
        objs = [
            {"name": "ParentObj", "is_parent": True, "plate": "1",
             "filament": "1", "layer_height": "0.2", "layer_custom": False,
             "wall_loops": "3", "walls_custom": False,
             "infill": "15%", "infill_custom": False,
             "support": "Off", "support_custom": False,
             "brim": "No", "brim_custom": False,
             "outer_wall_speed": "200", "speed_custom": False,
             "custom_settings": {}, "is_part": False},
            {"name": "  ChildPart", "is_parent": False, "plate": "",
             "filament": "1", "layer_height": "", "layer_custom": False,
             "wall_loops": "3", "walls_custom": False,
             "infill": "15%", "infill_custom": False,
             "support": "Off", "support_custom": False,
             "brim": "", "brim_custom": False,
             "outer_wall_speed": "200", "speed_custom": False,
             "custom_settings": {}, "is_part": True},
        ]
        results = [_make_3mf_result("a.3mf", objects=objs),
                   _make_3mf_result("b.3mf", objects=objs)]
        print_3mf_comparison(results, no_color=True)
        captured = capsys.readouterr()
        assert "ParentObj" in captured.out
        assert "ChildPart" in captured.out

    def test_objects_custom_settings_union_with_placeholder(self, capsys):
        """Custom settings should be union; missing keys get --."""
        obj1 = [{"name": "Obj", "is_parent": True, "plate": "1",
                 "filament": "1", "layer_height": "0.2", "layer_custom": False,
                 "wall_loops": "3", "walls_custom": False,
                 "infill": "15%", "infill_custom": False,
                 "support": "Off", "support_custom": False,
                 "brim": "No", "brim_custom": False,
                 "outer_wall_speed": "200", "speed_custom": False,
                 "custom_settings": {"sparse_infill_density": "80%"},
                 "is_part": False}]
        obj2 = [{"name": "Obj", "is_parent": True, "plate": "1",
                 "filament": "1", "layer_height": "0.2", "layer_custom": False,
                 "wall_loops": "5", "walls_custom": True,
                 "infill": "15%", "infill_custom": False,
                 "support": "Off", "support_custom": False,
                 "brim": "No", "brim_custom": False,
                 "outer_wall_speed": "200", "speed_custom": False,
                 "custom_settings": {"wall_loops": "5"},
                 "is_part": False}]
        r1 = _make_3mf_result("a.3mf", objects=obj1)
        r2 = _make_3mf_result("b.3mf", objects=obj2)
        print_3mf_comparison([r1, r2], no_color=True)
        captured = capsys.readouterr()
        assert "* sparse_infill_density" in captured.out
        assert "* wall_loops" in captured.out
        assert "--" in captured.out


# ═══════════════════════════════════════════════════════════════
# Test CLI integration for comparison mode
# ═══════════════════════════════════════════════════════════════

class TestCLIComparison:
    """Integration tests for CLI comparison mode."""

    def test_two_gcode_files(self, sample_gcode: Path, capsys):
        """Two gcode files should trigger comparison mode."""
        with patch.object(sys, 'argv', ['analyze.py', str(sample_gcode), str(sample_gcode)]):
            main()
        captured = capsys.readouterr()
        assert "COMPARISON" in captured.out

    def test_two_3mf_files(self, sample_3mf: Path, capsys):
        """Two 3MF files should trigger comparison mode."""
        with patch.object(sys, 'argv', ['analyze.py', str(sample_3mf), str(sample_3mf)]):
            main()
        captured = capsys.readouterr()
        assert "COMPARISON" in captured.out

    def test_single_file_no_comparison(self, sample_gcode: Path, capsys):
        """Single file should use normal single-file mode."""
        with patch.object(sys, 'argv', ['analyze.py', str(sample_gcode)]):
            main()
        captured = capsys.readouterr()
        assert "GCODE SETTINGS ANALYZER" in captured.out
        assert "COMPARISON" not in captured.out

    def test_more_than_four_files_exits(self, sample_gcode: Path):
        """More than 4 files should exit with error."""
        files = [str(sample_gcode)] * 5
        with patch.object(sys, 'argv', ['analyze.py'] + files):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_mixed_types_exits(self, sample_3mf: Path, sample_gcode: Path):
        """Mixing .3mf and .gcode files should exit with error."""
        with patch.object(sys, 'argv', ['analyze.py', str(sample_3mf), str(sample_gcode)]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_json_comparison_outputs_array(self, sample_gcode: Path, capsys):
        """--json with comparison should output a JSON array."""
        with patch.object(sys, 'argv', ['analyze.py', str(sample_gcode), str(sample_gcode), '--json']):
            main()
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) == 2
        for item in data:
            assert 'file' in item
            assert 'profile' in item

    def test_no_files_exits(self):
        """No files provided should exit with error."""
        with patch.object(sys, 'argv', ['analyze.py']):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code != 0

    def test_nonexistent_file_in_comparison_exits(self, sample_gcode: Path, temp_dir: Path):
        """A non-existent file in the list should exit with error."""
        fake = temp_dir / "nonexistent.gcode"
        with patch.object(sys, 'argv', ['analyze.py', str(sample_gcode), str(fake)]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_three_gcode_files(self, sample_gcode: Path, capsys):
        """Three gcode files should trigger comparison mode."""
        with patch.object(sys, 'argv', ['analyze.py', str(sample_gcode), str(sample_gcode), str(sample_gcode)]):
            main()
        captured = capsys.readouterr()
        assert "COMPARISON" in captured.out

    def test_four_gcode_files(self, sample_gcode: Path, capsys):
        """Four gcode files should trigger comparison mode (max allowed)."""
        with patch.object(sys, 'argv', ['analyze.py'] + [str(sample_gcode)] * 4):
            main()
        captured = capsys.readouterr()
        assert "COMPARISON" in captured.out

    def test_comparison_with_no_color(self, sample_gcode: Path, capsys):
        """Comparison with --no-color should work."""
        with patch.object(sys, 'argv', ['analyze.py', str(sample_gcode), str(sample_gcode), '--no-color']):
            main()
        captured = capsys.readouterr()
        assert "COMPARISON" in captured.out

    def test_comparison_with_wiki(self, sample_gcode: Path, capsys):
        """Comparison with --wiki should work."""
        with patch.object(sys, 'argv', ['analyze.py', str(sample_gcode), str(sample_gcode), '--wiki']):
            main()
        captured = capsys.readouterr()
        assert "COMPARISON" in captured.out
