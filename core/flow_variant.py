"""Snapmaker Orca flow-variant resolution (standard / high_flow).

Snapmaker Orca stores some process and filament settings as one value per
flow mode (e.g. ``inner_wall_speed = [150, 600]`` -> standard / high_flow).
The slicer picks the effective value at slicing time based on the filament's
``filament_volume_type``.

The logic below mirrors ``get_config_idx()`` / ``get_value_at()`` from
Snapmaker/OrcaSlicer v2.4.0 (src/libslic3r/PrintConfig.cpp, PrintConfig.hpp).
Files without ``*_flow_support`` keys are not affected.
"""

from typing import Callable, List, Optional, Sequence

FLOW_STANDARD = 'standard'
FLOW_HIGH_FLOW = 'high_flow'

FLOW_MODE_LABELS = {
    FLOW_STANDARD: 'Standard',
    FLOW_HIGH_FLOW: 'High Flow',
}

# process_flow_variant_options() in Snapmaker Orca v2.4.0
PROCESS_FLOW_KEYS = frozenset({
    'outer_wall_speed', 'inner_wall_speed', 'sparse_infill_speed',
    'internal_solid_infill_speed', 'top_surface_speed', 'gap_infill_speed',
    'bridge_speed', 'internal_bridge_speed', 'ironing_speed',
    'small_perimeter_speed', 'small_perimeter_threshold', 'support_speed',
    'support_interface_speed', 'initial_layer_speed',
    'initial_layer_infill_speed', 'initial_layer_travel_speed', 'travel_speed',
    'slow_down_layers', 'overhang_1_4_speed', 'overhang_2_4_speed',
    'overhang_3_4_speed', 'overhang_4_4_speed', 'enable_overhang_speed',
    'slowdown_for_curled_perimeters',
    'default_acceleration', 'outer_wall_acceleration', 'inner_wall_acceleration',
    'top_surface_acceleration', 'initial_layer_acceleration',
    'bridge_acceleration', 'travel_acceleration', 'sparse_infill_acceleration',
    'internal_solid_infill_acceleration', 'accel_to_decel_enable',
    'accel_to_decel_factor',
    'default_jerk', 'outer_wall_jerk', 'inner_wall_jerk', 'infill_jerk',
    'top_surface_jerk', 'initial_layer_jerk', 'travel_jerk',
    'default_junction_deviation',
    'max_volumetric_extrusion_rate_slope',
    'max_volumetric_extrusion_rate_slope_segment_length',
    'extrusion_rate_smoothing_external_perimeter_only',
})

# filament_flow_variant_options() in Snapmaker Orca v2.4.0
FILAMENT_FLOW_KEYS = frozenset({
    'filament_flow_ratio', 'enable_pressure_advance', 'pressure_advance',
    'nozzle_temperature_initial_layer', 'nozzle_temperature',
    'filament_max_volumetric_speed', 'fan_min_speed', 'fan_max_speed',
    'additional_cooling_fan_speed', 'filament_retraction_length',
    'filament_retraction_speed', 'filament_deretraction_speed',
    'filament_z_hop_types', 'filament_wipe_distance',
    'filament_retract_length_toolchange', 'filament_multitool_ramming',
    'filament_multitool_ramming_volume', 'filament_multitool_ramming_flow',
    'filament_minimal_purge_on_wipe_tower',
})


def _to_int(value: str, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


class FlowVariantResolver:
    """Resolves which list element of a flow-variant setting is in effect.

    Args:
        get_list: Callable returning the setting as a list of strings,
                  or None when the key is absent.
    """

    def __init__(self, get_list: Callable[[str], Optional[List[str]]]):
        self._volume_types: List[str] = get_list('filament_volume_type') or []
        self._process_support = get_list('process_flow_support')
        self._filament_support = get_list('filament_flow_support')
        self._step_sizes = get_list('filament_flow_step_size')
        self.enabled = (
            self._process_support is not None
            or self._filament_support is not None
        )

    def volume_type(self, filament_idx: int = 0) -> str:
        """Flow mode of a filament (0-based). Unknown values fall back to standard."""
        if 0 <= filament_idx < len(self._volume_types):
            vt = str(self._volume_types[filament_idx]).strip()
            if vt in FLOW_MODE_LABELS:
                return vt
        return FLOW_STANDARD

    def _step_size(self, filament_idx: int) -> int:
        if filament_idx >= len(self._step_sizes):
            return 1
        return max(1, _to_int(self._step_sizes[filament_idx], 1))

    def process_index(self, filament_idx: int = 0) -> int:
        """Index into a process flow-variant list for the given filament."""
        if not self._volume_types or self._process_support is None:
            return 0
        mode = self.volume_type(filament_idx)
        try:
            return self._process_support.index(mode)
        except ValueError:
            return 0

    def filament_index(self, filament_idx: int) -> int:
        """Index into a flattened filament flow-variant list for the given filament."""
        if not self._step_sizes:
            return filament_idx
        start = sum(self._step_size(i) for i in range(filament_idx))
        if not self._volume_types or self._filament_support is None:
            return start
        mode = self.volume_type(filament_idx)
        for pos in range(self._step_size(filament_idx)):
            if start + pos >= len(self._filament_support):
                break
            if self._filament_support[start + pos] == mode:
                return start + pos
        return start

    def index_for(self, key: str, filament_idx: int = 0) -> Optional[int]:
        """Return the effective index for a flow-variant key, or None if not applicable."""
        if not self.enabled:
            return None
        if key in PROCESS_FLOW_KEYS:
            return self.process_index(filament_idx)
        if key in FILAMENT_FLOW_KEYS:
            return self.filament_index(filament_idx)
        return None

    @staticmethod
    def pick(values: Sequence, index: int):
        """Mirror ConfigOptionVector::get_at(): out-of-range -> first element."""
        if not values:
            return None
        return values[index] if 0 <= index < len(values) else values[0]

    def resolve_per_filament(self, key: str, values: Sequence, n_filaments: int):
        """Effective value of a flow-variant key for each filament.

        Returns a single value when all filaments resolve to the same value,
        otherwise ``"F1: a, F2: b"``. Returns None if the key is not a
        flow-variant key (caller should use its own logic).
        """
        if self.index_for(key) is None:
            return None
        n = max(1, n_filaments)
        resolved = [self.pick(values, self.index_for(key, i)) for i in range(n)]
        if len(set(map(str, resolved))) == 1:
            return resolved[0]
        return ', '.join(f"F{i + 1}: {v}" for i, v in enumerate(resolved))

    def mode_label(self, n_filaments: int = 1) -> str:
        """Human-readable flow mode, e.g. 'Standard' or 'F1: Standard, F2: High Flow'."""
        if not self.enabled:
            return ''
        n = max(1, n_filaments)
        labels = [FLOW_MODE_LABELS[self.volume_type(i)] for i in range(n)]
        if len(set(labels)) == 1:
            return labels[0]
        return ', '.join(f"F{i + 1}: {lbl}" for i, lbl in enumerate(labels))
