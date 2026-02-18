"""Unit tests for core.field_defs module."""

import pytest

from core.field_defs import (
    # Factory helpers
    _fmt_plain,
    _fmt_mm,
    _fmt_speed,
    _fmt_temp,
    _fmt_green,
    _fmt_magenta,
    _if_present,
    # Global settings formatters
    _fmt_flow_ratio,
    _flow_label,
    _has_flow,
    _fmt_shell_layers,
    _fmt_support_toggle,
    _fmt_spiral,
    _cond_spiral,
    _fmt_ironing,
    _cond_ironing,
    _fmt_fuzzy,
    _cond_fuzzy,
    _fmt_fan,
    _cond_fan,
    _fmt_cooling,
    _cond_cooling,
    _fmt_features,
    _cond_features,
    # Statistics formatters
    _fmt_slicer,
    _fmt_file_size,
    _fmt_nozzle_diameter,
    _cond_nozzle_diameter,
    _fmt_filament_weight_total,
    _fmt_filament_list,
    _fmt_filament_cost_total,
    _cond_filament_cost_total,
    _fmt_filament_changes,
    _cond_filament_changes,
    _fmt_prime_tower,
    # Field definitions
    GLOBAL_SETTINGS_FIELDS,
    STATISTICS_FIELDS,
    RENDER_FILAMENT_NAMES,
    RENDER_FILAMENT_COLORS,
    FieldDef,
)


# ═══════════════════════════════════════════════════════════════
# Test factory helpers
# ═══════════════════════════════════════════════════════════════

class TestFmtPlain:
    """Tests for _fmt_plain factory."""

    def test_returns_value_as_string(self):
        fmt = _fmt_plain('key')
        assert fmt({'key': 'value'}) == 'value'

    def test_missing_key_returns_empty(self):
        fmt = _fmt_plain('key')
        assert fmt({}) == ''

    def test_numeric_value_converted(self):
        fmt = _fmt_plain('count')
        assert fmt({'count': 42}) == '42'


class TestFmtMm:
    """Tests for _fmt_mm factory."""

    def test_appends_mm_suffix(self):
        fmt = _fmt_mm('height')
        assert fmt({'height': '0.2'}) == '0.2 mm'

    def test_empty_value_returns_empty(self):
        fmt = _fmt_mm('height')
        assert fmt({'height': ''}) == ''

    def test_missing_key_returns_empty(self):
        fmt = _fmt_mm('height')
        assert fmt({}) == ''


class TestFmtSpeed:
    """Tests for _fmt_speed factory."""

    def test_formats_with_cyan_and_suffix(self):
        fmt = _fmt_speed('speed')
        assert fmt({'speed': '40'}) == '[cyan]40 mm/s[/cyan]'

    def test_empty_value_returns_empty(self):
        fmt = _fmt_speed('speed')
        assert fmt({'speed': ''}) == ''


class TestFmtTemp:
    """Tests for _fmt_temp factory."""

    def test_formats_with_red_and_degree(self):
        fmt = _fmt_temp('temp')
        result = fmt({'temp': '220'})
        assert '[red]' in result
        assert '220' in result
        assert '°C' in result

    def test_empty_value_returns_empty(self):
        fmt = _fmt_temp('temp')
        assert fmt({'temp': ''}) == ''


class TestFmtGreen:
    """Tests for _fmt_green factory."""

    def test_formats_with_green(self):
        fmt = _fmt_green('value')
        assert fmt({'value': 'test'}) == '[green]test[/green]'

    def test_empty_returns_empty(self):
        fmt = _fmt_green('value')
        assert fmt({'value': ''}) == ''


class TestFmtMagenta:
    """Tests for _fmt_magenta factory."""

    def test_formats_with_magenta(self):
        fmt = _fmt_magenta('value')
        assert fmt({'value': 'test'}) == '[magenta]test[/magenta]'


class TestIfPresent:
    """Tests for _if_present condition factory."""

    def test_true_when_value_present(self):
        cond = _if_present('key')
        assert cond({'key': 'value'}) is True

    def test_false_when_value_empty(self):
        cond = _if_present('key')
        assert cond({'key': ''}) is False

    def test_false_when_key_missing(self):
        cond = _if_present('key')
        assert cond({}) is False

    def test_false_when_value_none(self):
        cond = _if_present('key')
        assert cond({'key': None}) is False


# ═══════════════════════════════════════════════════════════════
# Test flow ratio helpers
# ═══════════════════════════════════════════════════════════════

class TestFlowRatio:
    """Tests for _flow_label and _fmt_flow_ratio helpers."""

    @pytest.mark.parametrize("profile, expected_label, expected_value", [
        ({'print_flow_ratio': '0.95', 'filament_flow_ratio': ''},
         "Print Flow Ratio", "95%"),
        ({'print_flow_ratio': '1', 'filament_flow_ratio': '0.966'},
         "Filament Flow Ratio", "0.966"),
        ({'print_flow_ratio': '', 'filament_flow_ratio': ''},
         "", ""),
        ({'print_flow_ratio': '1', 'filament_flow_ratio': '0.98'},
         "Filament Flow Ratio", "0.98"),
        ({'print_flow_ratio': '0.90', 'filament_flow_ratio': ''},
         "Print Flow Ratio", "90%"),
    ])
    def test_flow_ratio(self, profile, expected_label, expected_value):
        label, _ = _flow_label(profile)
        assert label == expected_label
        assert _fmt_flow_ratio(profile) == expected_value

    def test_has_flow_true_when_print_flow(self):
        assert _has_flow({'print_flow_ratio': '0.95'}) is True

    def test_has_flow_true_when_filament_flow(self):
        assert _has_flow({'filament_flow_ratio': '0.98'}) is True

    def test_has_flow_false_when_empty(self):
        assert _has_flow({}) is False

    def test_invalid_print_flow_ratio_returns_as_is(self):
        """Invalid float returns the raw value."""
        result = _fmt_flow_ratio({'print_flow_ratio': 'invalid'})
        assert result == 'invalid'


# ═══════════════════════════════════════════════════════════════
# Test global settings formatters
# ═══════════════════════════════════════════════════════════════

class TestShellLayers:
    """Tests for _fmt_shell_layers."""

    def test_formats_top_bottom(self):
        assert _fmt_shell_layers({'top_shell_layers': '4', 'bottom_shell_layers': '3'}) == '4/3'

    def test_handles_missing_keys(self):
        assert _fmt_shell_layers({}) == '/'


class TestSupportToggle:
    """Tests for _fmt_support_toggle."""

    def test_on_when_enabled(self):
        assert _fmt_support_toggle({'enable_support': '1'}) == 'On'

    def test_off_when_disabled(self):
        assert _fmt_support_toggle({'enable_support': '0'}) == 'Off'

    def test_off_when_missing(self):
        assert _fmt_support_toggle({}) == 'Off'


class TestSpiral:
    """Tests for _fmt_spiral and _cond_spiral."""

    def test_format_when_enabled(self):
        result = _fmt_spiral({'spiral_mode': '1'})
        assert 'ON' in result
        assert 'bright_green' in result

    def test_format_when_disabled(self):
        assert _fmt_spiral({'spiral_mode': '0'}) == ''

    def test_condition_true_when_enabled(self):
        assert _cond_spiral({'spiral_mode': '1'}) is True

    def test_condition_false_when_disabled(self):
        assert _cond_spiral({'spiral_mode': '0'}) is False


class TestIroning:
    """Tests for _fmt_ironing and _cond_ironing."""

    def test_format_when_has_type(self):
        result = _fmt_ironing({'ironing_type': 'top'})
        assert 'top' in result
        assert 'bright_green' in result

    def test_format_no_ironing(self):
        assert _fmt_ironing({'ironing_type': 'no ironing'}) == ''
        assert _fmt_ironing({'ironing_type': 'no_ironing'}) == ''

    def test_condition_true_when_has_type(self):
        assert _cond_ironing({'ironing_type': 'top'}) is True

    def test_condition_false_for_no_ironing(self):
        assert _cond_ironing({'ironing_type': 'no ironing'}) is False


class TestFuzzy:
    """Tests for _fmt_fuzzy and _cond_fuzzy."""

    def test_format_when_has_value(self):
        result = _fmt_fuzzy({'fuzzy_skin': 'all'})
        assert 'all' in result
        assert 'bright_green' in result

    def test_format_none(self):
        assert _fmt_fuzzy({'fuzzy_skin': 'none'}) == ''

    def test_condition_true_when_has_value(self):
        assert _cond_fuzzy({'fuzzy_skin': 'all'}) is True

    def test_condition_false_for_none(self):
        assert _cond_fuzzy({'fuzzy_skin': 'none'}) is False


class TestFan:
    """Tests for _fmt_fan and _cond_fan."""

    def test_formats_min_max(self):
        assert _fmt_fan({'fan_min_speed': '30', 'fan_max_speed': '100'}) == '30% / 100%'

    def test_handles_only_min(self):
        assert _fmt_fan({'fan_min_speed': '30', 'fan_max_speed': ''}) == '30% / %'

    def test_empty_when_both_missing(self):
        assert _fmt_fan({}) == ''

    def test_condition_true_when_has_speeds(self):
        assert _cond_fan({'fan_min_speed': '30'}) is True

    def test_condition_false_when_empty(self):
        assert _cond_fan({}) is False


class TestCooling:
    """Tests for _fmt_cooling and _cond_cooling."""

    def test_on_with_time(self):
        result = _fmt_cooling({'slow_down_for_layer_cooling': '1', 'slow_down_layer_time': '8'})
        assert 'On' in result
        assert '8s' in result

    def test_off_when_disabled(self):
        result = _fmt_cooling({'slow_down_for_layer_cooling': '0'})
        assert 'Off' in result

    def test_empty_when_missing(self):
        assert _fmt_cooling({}) == ''

    def test_condition_true_when_present(self):
        assert _cond_cooling({'slow_down_for_layer_cooling': '1'}) is True

    def test_condition_false_when_missing(self):
        assert _cond_cooling({}) is False


class TestFeatures:
    """Tests for _fmt_features helper."""

    def test_no_features(self):
        profile = {
            'enable_arc_fitting': '0',
            'enable_overhang_speed': '0',
            'timelapse_type': '0',
        }
        assert _fmt_features(profile) == ""

    def test_arc_fitting_enabled(self):
        profile = {
            'enable_arc_fitting': '1',
            'enable_overhang_speed': '0',
            'timelapse_type': '0',
        }
        result = _fmt_features(profile)
        assert "Enable Arc Fitting" in result

    def test_overhang_speed_enabled(self):
        profile = {
            'enable_arc_fitting': '0',
            'enable_overhang_speed': '1',
            'timelapse_type': '0',
        }
        result = _fmt_features(profile)
        assert "Enable Overhang Speed" in result

    def test_multiple_features(self):
        profile = {
            'enable_arc_fitting': '1',
            'enable_overhang_speed': '1',
            'timelapse_type': '0',
        }
        result = _fmt_features(profile)
        assert "Enable Arc Fitting" in result
        assert "Enable Overhang Speed" in result

    def test_timelapse_type(self):
        profile = {
            'enable_arc_fitting': '0',
            'enable_overhang_speed': '0',
            'timelapse_type': 'smooth',
        }
        result = _fmt_features(profile)
        assert "Timelapse Type: smooth" in result

    def test_missing_keys_handled(self):
        """Should handle missing keys gracefully."""
        assert _fmt_features({}) == ""

    def test_condition_true_when_has_features(self):
        assert _cond_features({'enable_arc_fitting': '1'}) is True

    def test_condition_false_when_no_features(self):
        assert _cond_features({'enable_arc_fitting': '0'}) is False


# ═══════════════════════════════════════════════════════════════
# Test statistics formatters
# ═══════════════════════════════════════════════════════════════

class TestSlicerFormatter:
    """Tests for _fmt_slicer."""

    def test_slicer_only(self):
        result = _fmt_slicer({'slicer': 'OrcaSlicer'})
        assert 'OrcaSlicer' in result
        assert 'cyan' in result

    def test_slicer_with_version(self):
        result = _fmt_slicer({'slicer': 'OrcaSlicer', 'slicer_version': '2.2.0'})
        assert 'OrcaSlicer 2.2.0' in result

    def test_empty_when_missing(self):
        assert _fmt_slicer({}) == ''


class TestFileSizeFormatter:
    """Tests for _fmt_file_size."""

    def test_bytes(self):
        assert _fmt_file_size({'file_size_bytes': 512}) == '512 B'

    def test_kilobytes(self):
        assert _fmt_file_size({'file_size_bytes': 2048}) == '2.0 KB'

    def test_megabytes(self):
        assert _fmt_file_size({'file_size_bytes': 2097152}) == '2.00 MB'

    def test_empty_when_missing(self):
        assert _fmt_file_size({}) == ''


class TestNozzleDiameter:
    """Tests for _fmt_nozzle_diameter and _cond_nozzle_diameter."""

    def test_formats_first_element(self):
        assert _fmt_nozzle_diameter({'nozzle_diameter': [0.4, 0.6]}) == '0.4 mm'

    def test_empty_when_not_list(self):
        assert _fmt_nozzle_diameter({'nozzle_diameter': '0.4'}) == ''

    def test_condition_true_for_list(self):
        assert _cond_nozzle_diameter({'nozzle_diameter': [0.4]}) is True

    def test_condition_false_for_empty_list(self):
        assert _cond_nozzle_diameter({'nozzle_diameter': []}) is False


class TestFilamentWeight:
    """Tests for _fmt_filament_weight_total."""

    def test_formats_with_suffix(self):
        result = _fmt_filament_weight_total({'filament_used_g': 12.345})
        assert '12.35 g' in result
        assert 'magenta' in result

    def test_empty_when_zero(self):
        assert _fmt_filament_weight_total({'filament_used_g': 0}) == ''


class TestFilamentList:
    """Tests for _fmt_filament_list."""

    def test_single_value(self):
        assert _fmt_filament_list(['10'], ' g') == '10 g'

    def test_multiple_values(self):
        assert _fmt_filament_list(['10', '20'], ' g') == '10 g, 20 g'

    def test_empty_list(self):
        assert _fmt_filament_list([], ' g') == ''


class TestFilamentCost:
    """Tests for _fmt_filament_cost_total and _cond_filament_cost_total."""

    def test_formats_with_dollar(self):
        result = _fmt_filament_cost_total({'filament_cost': 1.50})
        assert '$1.50' in result
        assert 'gold1' in result

    def test_empty_when_zero(self):
        assert _fmt_filament_cost_total({'filament_cost': 0}) == ''

    def test_condition_true_when_positive(self):
        assert _cond_filament_cost_total({'filament_cost': 1.0}) is True

    def test_condition_false_when_zero(self):
        assert _cond_filament_cost_total({'filament_cost': 0}) is False


class TestFilamentChanges:
    """Tests for _fmt_filament_changes and _cond_filament_changes."""

    def test_formats_count(self):
        assert _fmt_filament_changes({'filament_changes': 5}) == '5'

    def test_empty_when_zero(self):
        assert _fmt_filament_changes({'filament_changes': 0}) == ''

    def test_condition_true_when_positive(self):
        assert _cond_filament_changes({'filament_changes': 3}) is True

    def test_condition_false_when_zero(self):
        assert _cond_filament_changes({'filament_changes': 0}) is False


class TestPrimeTower:
    """Tests for _fmt_prime_tower."""

    def test_on_format(self):
        result = _fmt_prime_tower({'enable_prime_tower': '1'})
        assert 'On' in result
        assert 'green' in result

    def test_off_format(self):
        result = _fmt_prime_tower({'enable_prime_tower': '0'})
        assert 'Off' in result
        assert 'dim' in result

    def test_empty_when_missing(self):
        assert _fmt_prime_tower({}) == ''


# ═══════════════════════════════════════════════════════════════
# Test field definition structures
# ═══════════════════════════════════════════════════════════════

class TestFieldDefinitions:
    """Tests for field definition lists."""

    def test_global_settings_fields_is_list(self):
        assert isinstance(GLOBAL_SETTINGS_FIELDS, list)

    def test_statistics_fields_is_list(self):
        assert isinstance(STATISTICS_FIELDS, list)

    def test_render_sentinels_are_tuples(self):
        assert isinstance(RENDER_FILAMENT_NAMES, tuple)
        assert isinstance(RENDER_FILAMENT_COLORS, tuple)

    def test_global_fields_structure(self):
        """Each non-None field should be a 4-tuple with correct types."""
        for field in GLOBAL_SETTINGS_FIELDS:
            if field is None:
                continue
            if field is RENDER_FILAMENT_NAMES or field is RENDER_FILAMENT_COLORS:
                continue
            assert len(field) == 4, f"Field should have 4 elements: {field}"
            label, wiki_key, formatter, condition = field
            assert callable(label) or isinstance(label, str)
            assert isinstance(wiki_key, str)
            assert callable(formatter)
            assert condition is None or callable(condition)

    def test_statistics_fields_structure(self):
        """Each non-None field should be a 4-tuple with correct types."""
        for field in STATISTICS_FIELDS:
            if field is None:
                continue
            if field is RENDER_FILAMENT_NAMES or field is RENDER_FILAMENT_COLORS:
                continue
            assert len(field) == 4, f"Field should have 4 elements: {field}"
            label, wiki_key, formatter, condition = field
            assert callable(label) or isinstance(label, str)
            assert isinstance(wiki_key, str)
            assert callable(formatter)
            assert condition is None or callable(condition)

    def test_global_fields_has_separators(self):
        """Should contain None separators for visual grouping."""
        assert None in GLOBAL_SETTINGS_FIELDS

    def test_statistics_fields_has_separators(self):
        """Should contain None separators for visual grouping."""
        assert None in STATISTICS_FIELDS
