"""Unit tests for settings_wiki.py module."""

import json
import tempfile
import threading
from pathlib import Path
from typing import Optional
from unittest.mock import patch, MagicMock

import pytest

# Import module under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from settings_wiki import (
    _parse_print_config,
    _parse_tab_cpp,
    get_wiki_url,
    get_setting_info,
    get_all_settings,
    get_meta,
    WIKI_BASE,
    _TYPE_MAP,
    _WIKI_FALLBACKS,
)


# ═══════════════════════════════════════════════════════════════
# Test _parse_print_config
# ═══════════════════════════════════════════════════════════════

class TestParsePrintConfig:
    """Tests for C++ PrintConfig.cpp parser."""

    def test_extracts_basic_setting(self, sample_printconfig_cpp: str):
        """Should extract basic setting with label."""
        result = _parse_print_config(sample_printconfig_cpp)
        
        assert 'layer_height' in result
        assert result['layer_height']['label'] == 'Layer height'

    def test_extracts_category(self, sample_printconfig_cpp: str):
        """Should extract setting category."""
        result = _parse_print_config(sample_printconfig_cpp)
        
        assert result['layer_height']['category'] == 'Quality'
        assert result['wall_loops']['category'] == 'Strength'

    def test_extracts_tooltip(self, sample_printconfig_cpp: str):
        """Should extract setting tooltip."""
        result = _parse_print_config(sample_printconfig_cpp)
        
        assert 'tooltip' in result['layer_height']
        assert 'Layer height' in result['layer_height']['tooltip']

    def test_extracts_sidetext_unit(self, sample_printconfig_cpp: str):
        """Should extract sidetext (unit)."""
        result = _parse_print_config(sample_printconfig_cpp)
        
        assert result['layer_height']['sidetext'] == 'mm'

    def test_extracts_type(self, sample_printconfig_cpp: str):
        """Should extract and convert C++ type to human-readable."""
        result = _parse_print_config(sample_printconfig_cpp)
        
        assert result['layer_height']['type'] == 'float'
        assert result['wall_loops']['type'] == 'int'
        assert result['enable_support']['type'] == 'bool'

    def test_extracts_default_value(self, sample_printconfig_cpp: str):
        """Should extract default values."""
        result = _parse_print_config(sample_printconfig_cpp)
        
        assert result['layer_height']['default'] == '0.2'
        assert result['wall_loops']['default'] == '2'
        assert result['enable_support']['default'] == 'false'

    def test_extracts_full_label(self, sample_printconfig_cpp: str):
        """Should extract full_label when present."""
        result = _parse_print_config(sample_printconfig_cpp)
        
        assert result['wall_loops']['full_label'] == 'Number of wall loops'

    def test_skips_settings_without_label(self):
        """Settings without label should not be included."""
        cpp_without_label = '''
        def = this->add("internal_setting", coInt);
        def->set_default_value(new ConfigOptionInt(5));
        '''
        result = _parse_print_config(cpp_without_label)
        
        assert 'internal_setting' not in result

    def test_handles_empty_input(self):
        """Should handle empty input gracefully."""
        result = _parse_print_config('')
        
        assert result == {}


# ═══════════════════════════════════════════════════════════════
# Test _parse_tab_cpp
# ═══════════════════════════════════════════════════════════════

class TestParseTabCpp:
    """Tests for C++ Tab.cpp parser."""

    def test_extracts_direct_wiki_mapping(self, sample_tab_cpp: str):
        """Should extract direct append_single_option_line mappings."""
        result = _parse_tab_cpp(sample_tab_cpp)
        
        assert result['layer_height'] == 'quality_settings_layer_height'
        assert result['wall_loops'] == 'quality_settings_walls'

    def test_extracts_label_path_mapping(self, sample_tab_cpp: str):
        """Should extract label_path + get_option mappings."""
        result = _parse_tab_cpp(sample_tab_cpp)
        
        # support_type is mapped via label_path = "support_settings_enable"
        assert result['support_type'] == 'support_settings_enable'

    def test_direct_mapping_takes_priority(self):
        """Direct mapping should take priority over label_path."""
        cpp_with_both = '''
        line.label_path = "old_page";
        line.append_option(optgroup->get_option("my_setting"));
        optgroup->append_single_option_line("my_setting", "new_page");
        '''
        result = _parse_tab_cpp(cpp_with_both)
        
        # Direct mapping should win
        assert result['my_setting'] == 'new_page'

    def test_handles_empty_input(self):
        """Should handle empty input gracefully."""
        result = _parse_tab_cpp('')
        
        assert result == {}


# ═══════════════════════════════════════════════════════════════
# Test get_wiki_url
# ═══════════════════════════════════════════════════════════════

class TestGetWikiUrl:
    """Tests for get_wiki_url public API function."""

    def test_returns_url_for_known_setting(self):
        """Should return full URL for settings with wiki_page."""
        # This test depends on actual data, so we mock
        with patch('settings_wiki._load_cache') as mock_cache:
            mock_cache.return_value = {
                '_meta': {'wiki_base': 'https://example.com/wiki/'},
                'settings': {
                    'layer_height': {'wiki_page': 'quality_settings#layer'}
                }
            }
            
            url = get_wiki_url('layer_height')
            assert url == 'https://example.com/wiki/quality_settings#layer'

    def test_returns_none_for_unknown_setting(self):
        """Should return None for unknown settings."""
        with patch('settings_wiki._load_cache') as mock_cache:
            mock_cache.return_value = {
                '_meta': {},
                'settings': {}
            }
            
            url = get_wiki_url('totally_unknown_setting')
            assert url is None

    def test_returns_none_when_no_wiki_page(self):
        """Should return None when setting exists but has no wiki_page."""
        with patch('settings_wiki._load_cache') as mock_cache:
            mock_cache.return_value = {
                '_meta': {},
                'settings': {
                    'some_setting': {'label': 'Some Setting'}  # No wiki_page
                }
            }
            
            url = get_wiki_url('some_setting')
            assert url is None


# ═══════════════════════════════════════════════════════════════
# Test get_setting_info
# ═══════════════════════════════════════════════════════════════

class TestGetSettingInfo:
    """Tests for get_setting_info public API function."""

    def test_returns_dict_for_known_setting(self):
        """Should return full metadata dict for known settings."""
        with patch('settings_wiki._load_cache') as mock_cache:
            mock_cache.return_value = {
                '_meta': {},
                'settings': {
                    'layer_height': {
                        'label': 'Layer height',
                        'category': 'Quality',
                        'type': 'float',
                        'wiki_page': 'quality#layer'
                    }
                }
            }
            
            info = get_setting_info('layer_height')
            assert info['label'] == 'Layer height'
            assert info['category'] == 'Quality'
            assert info['type'] == 'float'

    def test_returns_none_for_unknown_setting(self):
        """Should return None for unknown settings."""
        with patch('settings_wiki._load_cache') as mock_cache:
            mock_cache.return_value = {
                '_meta': {},
                'settings': {}
            }
            
            info = get_setting_info('unknown_setting')
            assert info is None


# ═══════════════════════════════════════════════════════════════
# Test get_all_settings
# ═══════════════════════════════════════════════════════════════

class TestGetAllSettings:
    """Tests for get_all_settings public API function."""

    def test_returns_all_settings(self):
        """Should return complete settings dictionary."""
        with patch('settings_wiki._load_cache') as mock_cache:
            mock_data = {
                '_meta': {},
                'settings': {
                    'setting_a': {'label': 'A'},
                    'setting_b': {'label': 'B'},
                }
            }
            mock_cache.return_value = mock_data
            
            all_settings = get_all_settings()
            assert 'setting_a' in all_settings
            assert 'setting_b' in all_settings

    def test_returns_empty_dict_when_no_settings(self):
        """Should return empty dict when no settings loaded."""
        with patch('settings_wiki._load_cache') as mock_cache:
            mock_cache.return_value = {'_meta': {}, 'settings': {}}
            
            all_settings = get_all_settings()
            assert all_settings == {}


# ═══════════════════════════════════════════════════════════════
# Test get_meta
# ═══════════════════════════════════════════════════════════════

class TestGetMeta:
    """Tests for get_meta public API function."""

    def test_returns_metadata(self):
        """Should return metadata dictionary."""
        with patch('settings_wiki._load_cache') as mock_cache:
            mock_cache.return_value = {
                '_meta': {
                    'updated': '2025-01-01 12:00 UTC',
                    'wiki_base': 'https://example.com/wiki/',
                    'total_settings': 100
                },
                'settings': {}
            }
            
            meta = get_meta()
            assert meta['updated'] == '2025-01-01 12:00 UTC'
            assert meta['total_settings'] == 100


# ═══════════════════════════════════════════════════════════════
# Test TYPE_MAP constant
# ═══════════════════════════════════════════════════════════════

class TestTypeMap:
    """Tests for C++ type mapping constant."""

    def test_maps_common_types(self):
        """Should map common C++ types correctly."""
        assert _TYPE_MAP['coFloat'] == 'float'
        assert _TYPE_MAP['coInt'] == 'int'
        assert _TYPE_MAP['coBool'] == 'bool'
        assert _TYPE_MAP['coPercent'] == 'percent'
        assert _TYPE_MAP['coString'] == 'string'
        assert _TYPE_MAP['coEnum'] == 'enum'

    def test_maps_plural_types(self):
        """Should map plural C++ types (arrays)."""
        assert _TYPE_MAP['coFloats'] == 'float'
        assert _TYPE_MAP['coInts'] == 'int'
        assert _TYPE_MAP['coBools'] == 'bool'


# ═══════════════════════════════════════════════════════════════
# Test WIKI_FALLBACKS constant
# ═══════════════════════════════════════════════════════════════

class TestWikiFallbacks:
    """Tests for manual fallback wiki mappings."""

    def test_contains_known_fallbacks(self):
        """Should contain expected fallback mappings."""
        assert 'bridge_speed' in _WIKI_FALLBACKS
        assert 'bed_temperature' in _WIKI_FALLBACKS

    def test_fallback_values_are_strings(self):
        """Fallback values should be wiki page strings."""
        for key, value in _WIKI_FALLBACKS.items():
            assert isinstance(value, str)
            assert len(value) > 0


# ═══════════════════════════════════════════════════════════════
# Test thread safety
# ═══════════════════════════════════════════════════════════════

class TestThreadSafety:
    """Tests for thread-safe cache loading."""

    def test_concurrent_load_cache_is_safe(self):
        """Multiple threads loading cache should not cause issues."""
        results = []
        errors = []
        
        def load_and_store():
            try:
                with patch('settings_wiki._JSON_PATH') as mock_path:
                    mock_path.exists.return_value = False
                    # Simulate cache already set
                    import settings_wiki
                    settings_wiki._cache = {'_meta': {}, 'settings': {}}
                    
                    data = get_all_settings()
                    results.append(data)
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = [threading.Thread(target=load_and_store) for _ in range(10)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # No errors should occur
        assert len(errors) == 0
        # All results should be dictionaries
        assert all(isinstance(r, dict) for r in results)
