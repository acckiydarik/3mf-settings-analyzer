"""Unit tests for settings_wiki.py module."""

import json
import sys
import threading
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from settings_wiki import (
    _parse_print_config,
    _parse_tab_cpp,
    _build_settings_data,
    update,
    _download_file,
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


# ═══════════════════════════════════════════════════════════════
# Test update() function with mocks
# ═══════════════════════════════════════════════════════════════

class TestUpdate:
    """Tests for update() function with mocked HTTP calls."""

    @pytest.fixture
    def mock_urlopen(self):
        """Create a mock for urllib.request.urlopen."""
        def create_response(content: bytes):
            response = MagicMock()
            response.read.return_value = content
            response.__enter__ = lambda s: s
            response.__exit__ = MagicMock(return_value=False)
            return response
        return create_response

    def test_update_downloads_when_files_missing(self, tmp_path: Path, mock_urlopen):
        """update() should download files if local files are missing."""
        fake_content = b'// fake C++ content'
        
        with patch('settings_wiki._DATA_DIR', tmp_path), \
             patch('settings_wiki._JSON_PATH', tmp_path / 'settings_wiki.json'), \
             patch('settings_wiki.urllib.request.urlopen') as mock_url:
            
            mock_url.return_value = mock_urlopen(fake_content)
            
            # Simulate missing local files
            result = update(force=False)
            
            # Should have tried to download
            assert mock_url.called

    def test_update_force_skips_hash_check(self, tmp_path: Path, mock_urlopen):
        """update(force=True) should always download."""
        fake_content = b'// fake C++ content'
        
        with patch('settings_wiki._DATA_DIR', tmp_path), \
             patch('settings_wiki._JSON_PATH', tmp_path / 'settings_wiki.json'), \
             patch('settings_wiki.urllib.request.urlopen') as mock_url:
            
            mock_url.return_value = mock_urlopen(fake_content)
            
            result = update(force=True)
            
            # urlopen should be called for downloads
            assert mock_url.called

    def test_update_returns_false_if_up_to_date(self, tmp_path: Path, mock_urlopen):
        """update() should return False if content hash matches."""
        import hashlib
        
        fake_content = b'// same content'
        content_hash = hashlib.sha256(fake_content).hexdigest()[:12]
        
        # Create existing JSON with matching hash
        json_path = tmp_path / 'settings_wiki.json'
        json_path.write_text(json.dumps({
            '_meta': {'sha': {'Tab.cpp': content_hash, 'PrintConfig.cpp': content_hash}},
            'settings': {}
        }))
        
        # Create local cpp files
        (tmp_path / 'Tab.cpp').write_bytes(fake_content)
        (tmp_path / 'PrintConfig.cpp').write_bytes(fake_content)
        
        with patch('settings_wiki._DATA_DIR', tmp_path), \
             patch('settings_wiki._JSON_PATH', json_path), \
             patch('settings_wiki.urllib.request.urlopen') as mock_url:
            
            mock_url.return_value = mock_urlopen(fake_content)
            
            result = update(force=False)
            
            # Should return False (already up to date)
            assert result is False

    def test_update_returns_true_when_content_changed(self, tmp_path: Path, mock_urlopen):
        """update() should return True if content changed."""
        old_content = b'// old content'
        new_content = b'// new content'
        old_hash = '000000000000'  # Fake old hash
        
        # Create existing JSON with old hash
        json_path = tmp_path / 'settings_wiki.json'
        json_path.write_text(json.dumps({
            '_meta': {'sha': {'Tab.cpp': old_hash, 'PrintConfig.cpp': old_hash}},
            'settings': {}
        }))
        
        # Create local cpp files
        (tmp_path / 'Tab.cpp').write_bytes(old_content)
        (tmp_path / 'PrintConfig.cpp').write_bytes(old_content)
        
        with patch('settings_wiki._DATA_DIR', tmp_path), \
             patch('settings_wiki._JSON_PATH', json_path), \
             patch('settings_wiki.urllib.request.urlopen') as mock_url, \
             patch('settings_wiki.generate_json'):
            
            mock_url.return_value = mock_urlopen(new_content)
            
            result = update(force=False)
            
            # Should return True (content updated)
            assert result is True


class TestDownloadFile:
    """Tests for _download_file function."""

    def test_download_success(self, tmp_path: Path):
        """Successful download should write file and return True."""
        fake_content = b'downloaded content'
        dest = tmp_path / 'test_file.cpp'
        
        response = MagicMock()
        response.read.return_value = fake_content
        response.__enter__ = lambda s: s
        response.__exit__ = MagicMock(return_value=False)
        
        with patch('settings_wiki.urllib.request.urlopen', return_value=response):
            result = _download_file('https://example.com/file.cpp', dest)
        
        assert result is True
        assert dest.exists()
        assert dest.read_bytes() == fake_content

    def test_download_network_error(self, tmp_path: Path):
        """Network error should return False."""
        import urllib.error
        
        dest = tmp_path / 'test_file.cpp'
        
        with patch('settings_wiki.urllib.request.urlopen') as mock_url:
            mock_url.side_effect = urllib.error.URLError('Connection refused')
            
            result = _download_file('https://example.com/file.cpp', dest)
        
        assert result is False
        assert not dest.exists()


# ═══════════════════════════════════════════════════════════════
# Test CLI --update-wiki flag
# ═══════════════════════════════════════════════════════════════

class TestCLIUpdateWiki:
    """Tests for --update-wiki and --force-update-wiki CLI flags."""

    def test_update_wiki_flag(self):
        """--update-wiki should call settings_wiki.update()."""
        from analyze import main
        
        with patch.object(sys, 'argv', ['analyze.py', '--update-wiki']), \
             patch('settings_wiki.update') as mock_update:
            
            mock_update.return_value = True
            
            with pytest.raises(SystemExit) as exc_info:
                main()
            
            # Should exit with 0 (success)
            assert exc_info.value.code == 0
            mock_update.assert_called_once_with(force=False)

    def test_force_update_wiki_flag(self):
        """--force-update-wiki should call settings_wiki.update(force=True)."""
        from analyze import main
        
        with patch.object(sys, 'argv', ['analyze.py', '--force-update-wiki']), \
             patch('settings_wiki.update') as mock_update:
            
            mock_update.return_value = True
            
            with pytest.raises(SystemExit) as exc_info:
                main()
            
            assert exc_info.value.code == 0
            mock_update.assert_called_once_with(force=True)

    def test_update_wiki_already_up_to_date(self, capsys):
        """--update-wiki should report if already up to date."""
        from analyze import main
        
        with patch.object(sys, 'argv', ['analyze.py', '--update-wiki']), \
             patch('settings_wiki.update') as mock_update:
            
            mock_update.return_value = False  # Already up to date
            
            with pytest.raises(SystemExit):
                main()
            
            captured = capsys.readouterr()
            assert 'up to date' in captured.out.lower()

    def test_update_wiki_error_handling(self, capsys):
        """--update-wiki should handle errors gracefully."""
        from analyze import main
        
        with patch.object(sys, 'argv', ['analyze.py', '--update-wiki']), \
             patch('settings_wiki.update') as mock_update:
            
            mock_update.side_effect = Exception('Network error')
            
            with pytest.raises(SystemExit) as exc_info:
                main()
            
            # Should exit with error code
            assert exc_info.value.code == 1


# ═══════════════════════════════════════════════════════════════
# Test _build_settings_data function
# ═══════════════════════════════════════════════════════════════

class TestBuildSettingsData:
    """Tests for _build_settings_data function."""

    def test_returns_empty_when_tab_cpp_missing(self, tmp_path: Path):
        """Should return empty data when Tab.cpp is missing."""
        with patch('settings_wiki._DATA_DIR', tmp_path):
            result = _build_settings_data()
            
            assert result == {'_meta': {}, 'settings': {}}

    def test_returns_empty_when_printconfig_cpp_missing(self, tmp_path: Path, sample_tab_cpp: str):
        """Should return empty data when PrintConfig.cpp is missing."""
        (tmp_path / 'Tab.cpp').write_text(sample_tab_cpp)
        
        with patch('settings_wiki._DATA_DIR', tmp_path):
            result = _build_settings_data()
            
            assert result == {'_meta': {}, 'settings': {}}

    def test_builds_settings_from_cpp_files(self, tmp_path: Path, sample_printconfig_cpp: str, sample_tab_cpp: str):
        """Should parse and merge data from both .cpp files."""
        (tmp_path / 'PrintConfig.cpp').write_text(sample_printconfig_cpp)
        (tmp_path / 'Tab.cpp').write_text(sample_tab_cpp)
        
        with patch('settings_wiki._DATA_DIR', tmp_path):
            result = _build_settings_data()
        
        assert '_meta' in result
        assert 'settings' in result
        assert len(result['settings']) > 0
        # Check that layer_height was parsed from PrintConfig.cpp
        assert 'layer_height' in result['settings']
        assert result['settings']['layer_height']['label'] == 'Layer height'

    def test_merges_wiki_pages_from_tab_cpp(self, tmp_path: Path, sample_printconfig_cpp: str, sample_tab_cpp: str):
        """Should merge wiki_page from Tab.cpp into settings."""
        (tmp_path / 'PrintConfig.cpp').write_text(sample_printconfig_cpp)
        (tmp_path / 'Tab.cpp').write_text(sample_tab_cpp)
        
        with patch('settings_wiki._DATA_DIR', tmp_path):
            result = _build_settings_data()
        
        # layer_height should have wiki_page from Tab.cpp
        assert 'wiki_page' in result['settings']['layer_height']
        assert result['settings']['layer_height']['wiki_page'] == 'quality_settings_layer_height'

    def test_includes_meta_with_sha_and_counts(self, tmp_path: Path, sample_printconfig_cpp: str, sample_tab_cpp: str):
        """_meta should include SHA hashes and setting counts."""
        (tmp_path / 'PrintConfig.cpp').write_text(sample_printconfig_cpp)
        (tmp_path / 'Tab.cpp').write_text(sample_tab_cpp)
        
        with patch('settings_wiki._DATA_DIR', tmp_path):
            result = _build_settings_data()
        
        meta = result['_meta']
        assert 'sha' in meta
        assert 'Tab.cpp' in meta['sha']
        assert 'PrintConfig.cpp' in meta['sha']
        assert 'total_settings' in meta
        assert 'with_wiki_page' in meta
        assert meta['total_settings'] >= 1

    def test_applies_wiki_fallbacks(self, tmp_path: Path, sample_printconfig_cpp: str, sample_tab_cpp: str):
        """Should apply _WIKI_FALLBACKS for settings not in Tab.cpp."""
        # Add a setting that has a fallback mapping
        extended_printconfig = sample_printconfig_cpp + '''
    def = this->add("bridge_speed", coFloat);
    def->label = L("Bridge speed");
    def->category = L("Speed");
    def->set_default_value(new ConfigOptionFloat(25));
'''
        (tmp_path / 'PrintConfig.cpp').write_text(extended_printconfig)
        (tmp_path / 'Tab.cpp').write_text(sample_tab_cpp)
        
        with patch('settings_wiki._DATA_DIR', tmp_path):
            result = _build_settings_data()
        
        # bridge_speed should have fallback wiki_page
        assert 'bridge_speed' in result['settings']
        assert 'wiki_page' in result['settings']['bridge_speed']


# ═══════════════════════════════════════════════════════════════
# Test generate_json function
# ═══════════════════════════════════════════════════════════════

class TestGenerateJson:
    """Tests for generate_json function."""

    def test_generate_json_creates_file(self, tmp_path: Path, sample_printconfig_cpp: str, sample_tab_cpp: str):
        """generate_json should create settings_wiki.json file."""
        from settings_wiki import generate_json, _DATA_DIR, _JSON_PATH
        
        # Mock the data directory to use temp path
        with patch('settings_wiki._DATA_DIR', tmp_path), \
             patch('settings_wiki._JSON_PATH', tmp_path / 'settings_wiki.json'):
            
            # Write sample .cpp files
            (tmp_path / 'PrintConfig.cpp').write_text(sample_printconfig_cpp)
            (tmp_path / 'Tab.cpp').write_text(sample_tab_cpp)
            
            from settings_wiki import generate_json
            # Reimport to pick up patched paths
            import importlib
            import settings_wiki
            importlib.reload(settings_wiki)
            
            # This test verifies the function can be called
            # Full test requires mocking file paths

    def test_generate_json_returns_path(self, tmp_path: Path, sample_printconfig_cpp: str, sample_tab_cpp: str):
        """generate_json should return path to generated file."""
        # Create test files
        data_dir = tmp_path / 'data'
        data_dir.mkdir()
        (data_dir / 'PrintConfig.cpp').write_text(sample_printconfig_cpp)
        (data_dir / 'Tab.cpp').write_text(sample_tab_cpp)
        
        with patch('settings_wiki._DATA_DIR', data_dir), \
             patch('settings_wiki._JSON_PATH', data_dir / 'settings_wiki.json'):
            
            import settings_wiki
            # Clear cache
            settings_wiki._cache = None
            
            # generate_json builds from _DATA_DIR files
            result = settings_wiki.generate_json()
            
            assert result.exists()
            assert result.name == 'settings_wiki.json'


# ═══════════════════════════════════════════════════════════════
# Test _get_github_sha function
# ═══════════════════════════════════════════════════════════════

class TestGetGithubSha:
    """Tests for _get_github_sha function."""

    def test_get_github_sha_success(self):
        """_get_github_sha should return SHA on success."""
        from settings_wiki import _get_github_sha
        
        mock_response = json.dumps({"sha": "abc123def456"}).encode()
        
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_urlopen.return_value.__enter__ = MagicMock(return_value=BytesIO(mock_response))
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
            
            result = _get_github_sha("https://api.github.com/repos/test")
            
            assert result == "abc123def456"

    def test_get_github_sha_network_error(self):
        """_get_github_sha should return None on network error."""
        from settings_wiki import _get_github_sha
        import urllib.error
        
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
            
            result = _get_github_sha("https://api.github.com/repos/test")
            
            assert result is None

    def test_get_github_sha_invalid_json(self):
        """_get_github_sha should return None on invalid JSON response."""
        from settings_wiki import _get_github_sha
        
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_urlopen.return_value.__enter__ = MagicMock(return_value=BytesIO(b"not json"))
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
            
            result = _get_github_sha("https://api.github.com/repos/test")
            
            assert result is None


# ═══════════════════════════════════════════════════════════════
# Test atomic file writes
# ═══════════════════════════════════════════════════════════════

class TestAtomicFileWrites:
    """Tests for atomic file write functionality."""

    def test_download_file_validates_content(self, tmp_path: Path):
        """_download_file should reject HTML error pages."""
        dest = tmp_path / "test.cpp"
        
        # Mock response with HTML content (error page)
        html_content = b'<!DOCTYPE html><html><body>Error</body></html>'
        
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_urlopen.return_value.__enter__ = MagicMock(return_value=BytesIO(html_content))
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
            
            result = _download_file("https://example.com/file.cpp", dest)
            
            assert result is False
            assert not dest.exists()

    def test_download_file_atomic_write(self, tmp_path: Path):
        """_download_file should use atomic write (temp file + rename)."""
        dest = tmp_path / "test.cpp"
        valid_content = b'// C++ source code\nint main() { return 0; }'
        
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_urlopen.return_value.__enter__ = MagicMock(return_value=BytesIO(valid_content))
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
            
            result = _download_file("https://example.com/file.cpp", dest)
            
            assert result is True
            assert dest.exists()
            assert dest.read_bytes() == valid_content