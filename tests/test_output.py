"""Unit tests for analyzer.output module."""

from pathlib import Path

import pytest

from analyzer.gcode import GcodeAnalyzer
from analyzer.output import (
    _find_nearest_css3_color,
    _format_file_size,
    _format_filament_list,
    _format_object_value,
    _format_support_value,
    _hex_to_color_name,
    _load_css3_colors,
    _make_wiki_helpers,
    print_gcode_results,
    print_results,
)
from analyzer.threemf import ThreeMFAnalyzer


# ═══════════════════════════════════════════════════════════════
# Test _make_wiki_helpers function
# ═══════════════════════════════════════════════════════════════

class TestMakeWikiHelpers:
    """Tests for _make_wiki_helpers helper factory."""

    def test_disabled_returns_passthrough_label(self):
        """When disabled, wiki_label should return display_name unchanged."""
        wiki_label, _ = _make_wiki_helpers(enabled=False)
        assert wiki_label("Layer Height", "layer_height") == "Layer Height"

    def test_disabled_returns_passthrough_key(self):
        """When disabled, wiki_key should return setting_key unchanged."""
        _, wiki_key = _make_wiki_helpers(enabled=False)
        assert wiki_key("layer_height") == "layer_height"

    def test_enabled_returns_callables(self):
        """When enabled, should return two callable objects."""
        wiki_label, wiki_key = _make_wiki_helpers(enabled=True)
        assert callable(wiki_label)
        assert callable(wiki_key)

    def test_enabled_label_returns_string(self):
        """When enabled, wiki_label should return a string (possibly with link markup)."""
        wiki_label, _ = _make_wiki_helpers(enabled=True)
        result = wiki_label("Layer Height", "layer_height")
        assert isinstance(result, str)
        assert "Layer Height" in result

    def test_enabled_key_returns_string(self):
        """When enabled, wiki_key should return a string (possibly with link markup)."""
        _, wiki_key = _make_wiki_helpers(enabled=True)
        result = wiki_key("layer_height")
        assert isinstance(result, str)
        assert "layer_height" in result


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
        assert '\u2190' not in result

    def test_custom_value_with_diff(self):
        """Custom value with diff mode should show asterisk and default."""
        result = _format_object_value('20', True, '10', True)
        assert '*20' in result
        assert '\u219010' in result
        assert 'bold yellow' in result

    def test_custom_value_diff_no_default(self):
        """Custom value with diff but no default should not show arrow."""
        result = _format_object_value('20', True, None, True)
        assert '*20' in result
        assert '\u2190' not in result

    def test_custom_value_diff_empty_default(self):
        """Custom value with empty default should not show arrow."""
        result = _format_object_value('20', True, '', True)
        assert '*20' in result
        assert '\u2190' not in result


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


# ═══════════════════════════════════════════════════════════════
# Test _find_nearest_css3_color
# ═══════════════════════════════════════════════════════════════

class TestFindNearestCss3Color:
    """Tests for nearest CSS3 color matching."""

    def test_exact_red(self):
        assert _find_nearest_css3_color(255, 0, 0) == 'Red'

    def test_exact_blue(self):
        assert _find_nearest_css3_color(0, 0, 255) == 'Blue'

    def test_exact_yellow(self):
        assert _find_nearest_css3_color(255, 255, 0) == 'Yellow'

    def test_exact_black(self):
        assert _find_nearest_css3_color(0, 0, 0) == 'Black'

    def test_exact_white(self):
        assert _find_nearest_css3_color(255, 255, 255) == 'White'

    def test_gold_amber_matches_gold(self):
        """#F0BE02 (240, 190, 2) should match 'Gold'."""
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
        name, style = _hex_to_color_name('#FF0000FF')
        assert name == 'Red'
        assert style == '#FF0000'

    def test_exact_blue(self):
        name, style = _hex_to_color_name('#0000FFFF')
        assert name == 'Blue'
        assert style == '#0000FF'

    def test_exact_yellow(self):
        name, style = _hex_to_color_name('#FFFF00FF')
        assert name == 'Yellow'
        assert style == '#FFFF00'

    def test_exact_black(self):
        name, style = _hex_to_color_name('#000000FF')
        assert name == 'Black'
        assert style == '#000000'

    def test_exact_white(self):
        name, style = _hex_to_color_name('#FFFFFFFF')
        assert name == 'White'
        assert style == '#FFFFFF'

    def test_exact_cyan(self):
        name, style = _hex_to_color_name('#00FFFFFF')
        assert name in ('Cyan', 'Aqua')
        assert style == '#00FFFF'

    def test_exact_magenta(self):
        name, style = _hex_to_color_name('#FF00FFFF')
        assert name in ('Magenta', 'Fuchsia')
        assert style == '#FF00FF'

    # --- Nearest-match (non-exact) ---

    def test_gold_amber_color(self):
        name, style = _hex_to_color_name('#F0BE02FF')
        assert name == 'Gold'
        assert style == '#F0BE02'

    def test_near_red(self):
        name, style = _hex_to_color_name('#DE1619FF')
        assert name == 'Crimson'
        assert style == '#DE1619'

    def test_dark_orange(self):
        name, style = _hex_to_color_name('#FF8000FF')
        assert name == 'DarkOrange'
        assert style == '#FF8000'

    def test_near_green(self):
        name, style = _hex_to_color_name('#00CC00FF')
        name_lower = name.lower()
        assert 'green' in name_lower or name == 'Lime'

    def test_near_purple(self):
        name, style = _hex_to_color_name('#9900CCFF')
        assert name == 'DarkViolet'
        assert style == '#9900CC'

    def test_pink_shade(self):
        name, style = _hex_to_color_name('#FFB0B0FF')
        name_lower = name.lower()
        assert 'pink' in name_lower or 'salmon' in name_lower or 'rose' in name_lower

    def test_gray_shades(self):
        name, _ = _hex_to_color_name('#808080FF')
        assert name == 'Gray'

        name, _ = _hex_to_color_name('#505050FF')
        assert 'Gray' in name or 'grey' in name.lower() or 'Slate' in name

        name, _ = _hex_to_color_name('#C0C0C0FF')
        assert name == 'Silver'

    # --- Style is always original hex ---

    def test_style_is_hex_for_all_colors(self):
        test_cases = ['#FF0000FF', '#00FF00', '#0000FF', '#F0BE02FF', '#000000FF']
        for hex_input in test_cases:
            _, style = _hex_to_color_name(hex_input)
            assert style.startswith('#'), f"Style for {hex_input} should start with #, got {style}"
            assert len(style) == 7, f"Style for {hex_input} should be #RRGGBB format, got {style}"

    # --- Format variations ---

    def test_rrggbb_format(self):
        name, style = _hex_to_color_name('#FF0000')
        assert name == 'Red'
        assert style == '#FF0000'

    def test_rrggbbaa_format(self):
        name, style = _hex_to_color_name('#00FF0080')
        name_lower = name.lower()
        assert 'green' in name_lower or name == 'Lime'
        assert style == '#00FF00'

    # --- Invalid inputs ---

    def test_empty_string(self):
        name, style = _hex_to_color_name('')
        assert name == ''
        assert style == 'white'

    def test_no_hash_prefix(self):
        name, style = _hex_to_color_name('FF0000')
        assert name == 'FF0000'
        assert style == 'white'

    def test_short_hex(self):
        name, style = _hex_to_color_name('#FFF')
        assert name == '#FFF'
        assert style == 'white'

    def test_non_hex_chars(self):
        name, style = _hex_to_color_name('#XYZXYZ')
        assert name == '#XYZXYZ'
        assert style == 'white'

    def test_none_input(self):
        name, style = _hex_to_color_name(None)
        assert name is None
        assert style == 'white'

    def test_every_color_gets_a_name(self):
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
# Test print_results / print_gcode_results
# ═══════════════════════════════════════════════════════════════

class TestPrintResults:
    """Tests for print_results function."""

    def test_print_results_basic(self, sample_3mf: Path):
        analyzer = ThreeMFAnalyzer(sample_3mf)
        result = analyzer.analyze()
        print_results(result)

    def test_print_results_diff_mode(self, sample_3mf: Path):
        analyzer = ThreeMFAnalyzer(sample_3mf)
        result = analyzer.analyze()
        print_results(result, show_diff=True)

    def test_print_results_no_color(self, sample_3mf: Path):
        analyzer = ThreeMFAnalyzer(sample_3mf)
        result = analyzer.analyze()
        print_results(result, no_color=True)

    def test_print_results_wiki_mode(self, sample_3mf: Path):
        analyzer = ThreeMFAnalyzer(sample_3mf)
        result = analyzer.analyze()
        print_results(result, wiki=True)


class TestPrintGcodeResults:
    """Tests for print_gcode_results function."""

    def test_print_gcode_results_basic(self, sample_gcode: Path):
        analyzer = GcodeAnalyzer(sample_gcode)
        result = analyzer.analyze()
        print_gcode_results(result)

    def test_print_gcode_results_diff_mode(self, sample_gcode: Path):
        analyzer = GcodeAnalyzer(sample_gcode)
        result = analyzer.analyze()
        print_gcode_results(result, show_diff=True)

    def test_print_gcode_results_no_color(self, sample_gcode: Path):
        analyzer = GcodeAnalyzer(sample_gcode)
        result = analyzer.analyze()
        print_gcode_results(result, no_color=True)

    def test_print_gcode_results_wiki_mode(self, sample_gcode: Path):
        analyzer = GcodeAnalyzer(sample_gcode)
        result = analyzer.analyze()
        print_gcode_results(result, wiki=True)
