"""Tests for Snapmaker Orca flow-variant resolution (standard / high_flow)."""

import io
from pathlib import Path

import pytest
from rich.console import Console

from core.flow_variant import (
    FILAMENT_FLOW_KEYS,
    PROCESS_FLOW_KEYS,
    FlowVariantResolver,
)
from core.gcode import GcodeAnalyzer
from core.output import _print_profile_panel
from core.threemf import ThreeMFAnalyzer


def _resolver(settings: dict) -> FlowVariantResolver:
    def get_list(key):
        val = settings.get(key)
        if val is None:
            return None
        return [str(v) for v in val] if isinstance(val, list) else [str(val)]
    return FlowVariantResolver(get_list)


# ═══════════════════════════════════════════════════════════════
# FlowVariantResolver
# ═══════════════════════════════════════════════════════════════

class TestFlowVariantResolver:

    def test_disabled_without_flow_support_keys(self):
        r = _resolver({'filament_volume_type': ['high_flow']})
        assert r.enabled is False
        assert r.index_for('inner_wall_speed') is None
        assert r.mode_label() == ''

    def test_non_flow_key_returns_none(self):
        r = _resolver({'process_flow_support': ['standard', 'high_flow']})
        assert r.index_for('wall_loops') is None

    @pytest.mark.parametrize("volume_type, expected", [
        (['standard'], 0),
        (['high_flow'], 1),
        (['bogus'], 0),
        ([], 0),
    ])
    def test_process_index(self, volume_type, expected):
        r = _resolver({
            'filament_volume_type': volume_type,
            'process_flow_support': ['standard', 'high_flow'],
        })
        assert r.process_index(0) == expected

    def test_process_index_mode_not_declared(self):
        r = _resolver({
            'filament_volume_type': ['high_flow'],
            'process_flow_support': ['standard'],
        })
        assert r.process_index(0) == 0

    def test_process_index_filament_beyond_volume_types_is_standard(self):
        r = _resolver({
            'filament_volume_type': ['high_flow'],
            'process_flow_support': ['standard', 'high_flow'],
        })
        assert r.process_index(3) == 0

    def test_filament_index_flattened_layout(self):
        # Real layout from a Snapmaker U1 project: filament 2 declares two variants.
        r = _resolver({
            'filament_volume_type': ['standard', 'standard', 'standard'],
            'filament_flow_support': ['standard', 'standard', 'high_flow', 'standard'],
            'filament_flow_step_size': ['1', '2', '1'],
        })
        assert [r.filament_index(i) for i in range(3)] == [0, 1, 3]

    def test_filament_index_high_flow_selects_variant_slot(self):
        r = _resolver({
            'filament_volume_type': ['high_flow', 'high_flow'],
            'filament_flow_support': ['standard', 'high_flow', 'standard', 'high_flow'],
            'filament_flow_step_size': ['2', '2'],
        })
        assert [r.filament_index(i) for i in range(2)] == [1, 3]

    def test_filament_index_undeclared_mode_uses_segment_start(self):
        r = _resolver({
            'filament_volume_type': ['high_flow'],
            'filament_flow_support': ['standard'],
            'filament_flow_step_size': ['1'],
        })
        assert r.filament_index(0) == 0

    def test_filament_index_without_step_sizes(self):
        r = _resolver({'filament_flow_support': ['standard', 'standard']})
        assert r.filament_index(1) == 1

    def test_pick_out_of_range_falls_back_to_first(self):
        assert FlowVariantResolver.pick(['150'], 1) == '150'
        assert FlowVariantResolver.pick([], 0) is None

    def test_resolve_per_filament_collapses_equal_values(self):
        r = _resolver({
            'filament_volume_type': ['standard', 'standard'],
            'process_flow_support': ['standard', 'high_flow'],
        })
        assert r.resolve_per_filament('inner_wall_speed', ['150', '600'], 2) == '150'

    def test_resolve_per_filament_labels_differing_values(self):
        r = _resolver({
            'filament_volume_type': ['standard', 'high_flow'],
            'process_flow_support': ['standard', 'high_flow'],
        })
        assert r.resolve_per_filament('inner_wall_speed', ['150', '600'], 2) == 'F1: 150, F2: 600'

    def test_mode_label(self):
        base = {'process_flow_support': ['standard', 'high_flow']}
        assert _resolver({**base, 'filament_volume_type': ['standard']}).mode_label(1) == 'Standard'
        assert _resolver({**base, 'filament_volume_type': ['high_flow']}).mode_label(1) == 'High Flow'
        mixed = _resolver({**base, 'filament_volume_type': ['standard', 'high_flow']})
        assert mixed.mode_label(2) == 'F1: Standard, F2: High Flow'

    def test_key_sets_are_disjoint(self):
        assert not (PROCESS_FLOW_KEYS & FILAMENT_FLOW_KEYS)


# ═══════════════════════════════════════════════════════════════
# ThreeMFAnalyzer integration
# ═══════════════════════════════════════════════════════════════

def _snapmaker_project(volume_type: str = 'standard') -> dict:
    return {
        'filament_settings_id': ['PLA'],
        'filament_volume_type': [volume_type],
        'process_flow_support': ['standard', 'high_flow'],
        'filament_flow_support': ['standard'],
        'filament_flow_step_size': ['1'],
        'inner_wall_speed': ['150', '600'],
        'outer_wall_speed': ['80', '500'],
        'nozzle_temperature': ['220'],
        'different_settings_to_system': ['inner_wall_speed;outer_wall_speed', '', ''],
    }


class TestThreeMFFlowVariants:

    @pytest.mark.parametrize("volume_type, inner, outer, label", [
        ('standard', '150', '80', 'Standard'),
        ('high_flow', '600', '500', 'High Flow'),
    ])
    def test_global_and_custom_use_active_mode(self, tmp_path, volume_type, inner, outer, label):
        analyzer = ThreeMFAnalyzer(tmp_path / 'x.3mf')
        analyzer.project_settings = _snapmaker_project(volume_type)

        assert analyzer._get_value('inner_wall_speed') == inner
        custom = analyzer._get_custom_global_settings()
        assert custom['inner_wall_speed'] == inner
        assert custom['outer_wall_speed'] == outer
        assert analyzer._get_profile_info()['flow_mode'] == label

    def test_filament_override_uses_flattened_index(self, tmp_path):
        analyzer = ThreeMFAnalyzer(tmp_path / 'x.3mf')
        analyzer.project_settings = {
            'filament_settings_id': ['A', 'B', 'C'],
            'filament_volume_type': ['standard', 'standard', 'standard'],
            'process_flow_support': ['standard'],
            'filament_flow_support': ['standard', 'standard', 'high_flow', 'standard'],
            'filament_flow_step_size': ['1', '2', '1'],
            'nozzle_temperature': ['215', '230', '230', '210'],
            'filament_type': ['PLA', 'PLA', 'PETG'],
            'different_settings_to_system': ['', '', '', 'nozzle_temperature;filament_type', ''],
        }
        custom = analyzer._get_custom_global_settings()
        assert custom['nozzle_temperature'] == '210'
        # Non-flow filament keys keep one value per filament
        assert custom['filament_type'] == 'PETG'

    def test_non_snapmaker_file_unchanged(self, tmp_path):
        analyzer = ThreeMFAnalyzer(tmp_path / 'x.3mf')
        analyzer.project_settings = {
            'filament_settings_id': ['PLA'],
            'inner_wall_speed': ['150', '600'],
            'different_settings_to_system': ['inner_wall_speed', '', ''],
        }
        assert analyzer._get_value('inner_wall_speed') == '150'
        assert analyzer._get_custom_global_settings()['inner_wall_speed'] == ['150', '600']
        assert analyzer._get_profile_info()['flow_mode'] == ''


# ═══════════════════════════════════════════════════════════════
# GcodeAnalyzer integration
# ═══════════════════════════════════════════════════════════════

def _write_gcode(path: Path, volume_types: str, filaments: str) -> Path:
    path.write_text(f"""; CONFIG_BLOCK_START
; different_settings_to_system = outer_wall_speed;pressure_advance
; filament_settings_id = {filaments}
; filament_volume_type = {volume_types}
; process_flow_support = standard,high_flow
; filament_flow_support = standard,standard
; filament_flow_step_size = 1,1
; outer_wall_speed = 80,200
; inner_wall_speed = 150,600
; pressure_advance = 0.02,0.032
; CONFIG_BLOCK_END
""", encoding='utf-8')
    return path


class TestGcodeFlowVariants:

    def test_flow_list_not_mislabelled_as_filaments(self, tmp_path):
        gcode = _write_gcode(tmp_path / 'a.gcode', 'standard,standard', '"PLA A";"PLA B"')
        result = GcodeAnalyzer(gcode).analyze()
        assert result['custom_global']['outer_wall_speed'] == '80'
        assert result['custom_global']['pressure_advance'] == 'F1: 0.02, F2: 0.032'
        assert result['profile']['inner_wall_speed'] == '150'
        assert result['profile']['flow_mode'] == 'Standard'

    def test_high_flow_filament(self, tmp_path):
        gcode = _write_gcode(tmp_path / 'b.gcode', 'high_flow,standard', '"PLA A";"PLA B"')
        result = GcodeAnalyzer(gcode).analyze()
        assert result['custom_global']['outer_wall_speed'] == 'F1: 200, F2: 80'
        assert result['profile']['inner_wall_speed'] == '600'
        assert result['profile']['flow_mode'] == 'F1: High Flow, F2: Standard'


# ═══════════════════════════════════════════════════════════════
# Output
# ═══════════════════════════════════════════════════════════════

class TestFlowModeOutput:

    def _render(self, profile: dict) -> str:
        buf = io.StringIO()
        _print_profile_panel(Console(file=buf, width=120), profile)
        return buf.getvalue()

    def test_flow_mode_row_shown(self):
        out = self._render({'printer': 'U1', 'process': 'P', 'filaments': ['F'],
                            'flow_mode': 'High Flow'})
        assert 'Flow Mode' in out and 'High Flow' in out

    def test_flow_mode_row_hidden_when_absent(self):
        out = self._render({'printer': 'P1S', 'process': 'P', 'filaments': ['F'],
                            'flow_mode': ''})
        assert 'Flow Mode' not in out
