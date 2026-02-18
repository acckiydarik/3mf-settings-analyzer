"""Unit tests for core.cli module."""

import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from core.cli import _get_file_type, main, setup_logging


# ═══════════════════════════════════════════════════════════════
# Test CLI / main() function
# ═══════════════════════════════════════════════════════════════

class TestCLI:
    """Tests for command-line interface and main() function."""

    def test_main_with_file(self, sample_3mf: Path):
        """main() should work with a valid 3MF file."""
        with patch.object(sys, 'argv', ['3mf-analyzer', str(sample_3mf)]):
            main()

    def test_main_json_output(self, sample_3mf: Path, capsys):
        """--json flag should output valid JSON."""
        with patch.object(sys, 'argv', ['3mf-analyzer', str(sample_3mf), '--json']):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert 'file' in data
        assert 'profile' in data
        assert 'rows' in data

    def test_main_diff_mode(self, sample_3mf: Path, capsys):
        """--diff flag should not cause errors."""
        with patch.object(sys, 'argv', ['3mf-analyzer', str(sample_3mf), '--diff']):
            main()

        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_main_no_color(self, sample_3mf: Path):
        """--no-color flag should work without errors."""
        with patch.object(sys, 'argv', ['3mf-analyzer', str(sample_3mf), '--no-color']):
            main()

    def test_main_wiki_mode(self, sample_3mf: Path):
        """--wiki flag should work without errors."""
        with patch.object(sys, 'argv', ['3mf-analyzer', str(sample_3mf), '--wiki']):
            main()

    def test_main_verbose_mode(self, sample_3mf: Path):
        """--verbose flag should enable debug logging."""
        with patch.object(sys, 'argv', ['3mf-analyzer', str(sample_3mf), '--verbose']):
            main()

    def test_main_combined_flags(self, sample_3mf: Path, capsys):
        """Multiple flags should work together."""
        with patch.object(sys, 'argv', ['3mf-analyzer', str(sample_3mf), '--diff', '--wiki', '--no-color']):
            main()

        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_main_missing_file_exits(self):
        """main() should exit with error if no file provided."""
        with patch.object(sys, 'argv', ['3mf-analyzer']):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code != 0

    def test_main_nonexistent_file_exits(self, temp_dir: Path):
        """main() should exit with error for non-existent file."""
        fake_path = temp_dir / "does_not_exist.3mf"
        with patch.object(sys, 'argv', ['3mf-analyzer', str(fake_path)]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_main_bad_zip_exits(self, temp_dir: Path):
        """main() should exit with error for invalid ZIP file."""
        bad_file = temp_dir / "bad.3mf"
        bad_file.write_text("not a zip")

        with patch.object(sys, 'argv', ['3mf-analyzer', str(bad_file)]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_main_version_output(self, capsys):
        """--version flag should print version and exit."""
        from core import __version__
        with patch.object(sys, 'argv', ['3mf-analyzer', '--version']):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert __version__ in captured.out

    def test_main_invalid_json_exits(self, invalid_json_3mf: Path):
        """main() should exit(1) when 3MF has invalid JSON project_settings."""
        with patch.object(sys, 'argv', ['3mf-analyzer', str(invalid_json_3mf)]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_main_invalid_xml_exits(self, invalid_xml_3mf: Path):
        """main() should exit(1) when 3MF has invalid XML model_settings."""
        with patch.object(sys, 'argv', ['3mf-analyzer', str(invalid_xml_3mf)]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_main_zip_slip_exits(self, malicious_3mf_traversal: Path):
        """main() should exit(1) when 3MF contains path traversal attack."""
        with patch.object(sys, 'argv', ['3mf-analyzer', str(malicious_3mf_traversal)]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1


# ═══════════════════════════════════════════════════════════════
# Test setup_logging
# ═══════════════════════════════════════════════════════════════

class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_default(self):
        """setup_logging() should set INFO level by default."""
        setup_logging(verbose=False)

    def test_setup_logging_verbose(self):
        """setup_logging(verbose=True) should set DEBUG level."""
        setup_logging(verbose=True)


# ═══════════════════════════════════════════════════════════════
# Test _get_file_type function
# ═══════════════════════════════════════════════════════════════

class TestGetFileType:
    """Tests for _get_file_type helper function."""

    @pytest.mark.parametrize("filename, expected", [
        ("test.3mf", "3mf"),
        ("test.3MF", "3mf"),
        ("test.gcode", "gcode"),
        ("test.GCODE", "gcode"),
        ("test.txt", "unknown"),
        ("test.stl", "unknown"),
    ])
    def test_detects_file_type(self, temp_dir: Path, filename, expected):
        path = temp_dir / filename
        path.touch()
        assert _get_file_type(path) == expected


# ═══════════════════════════════════════════════════════════════
# Test CLI with Gcode files
# ═══════════════════════════════════════════════════════════════

class TestGcodeCLI:
    """Tests for command-line interface with gcode files."""

    def test_main_with_gcode(self, sample_gcode: Path):
        """main() should work with a valid gcode file."""
        with patch.object(sys, 'argv', ['3mf-analyzer', str(sample_gcode)]):
            main()

    def test_main_gcode_json_output(self, sample_gcode: Path, capsys):
        """--json flag should output valid JSON for gcode."""
        with patch.object(sys, 'argv', ['3mf-analyzer', str(sample_gcode), '--json']):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert 'file' in data
        assert 'profile' in data
        assert 'statistics' in data
        assert 'objects' in data

    def test_main_gcode_diff_mode(self, sample_gcode: Path, capsys):
        """--diff flag should work with gcode files."""
        with patch.object(sys, 'argv', ['3mf-analyzer', str(sample_gcode), '--diff']):
            main()

        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_main_gcode_wiki_mode(self, sample_gcode: Path):
        """--wiki flag should work with gcode files."""
        with patch.object(sys, 'argv', ['3mf-analyzer', str(sample_gcode), '--wiki']):
            main()

    def test_main_gcode_no_color(self, sample_gcode: Path):
        """--no-color flag should work without errors for gcode."""
        with patch.object(sys, 'argv', ['3mf-analyzer', str(sample_gcode), '--no-color']):
            main()

    def test_main_gcode_verbose(self, sample_gcode: Path):
        """--verbose flag should work without errors for gcode."""
        with patch.object(sys, 'argv', ['3mf-analyzer', str(sample_gcode), '--verbose']):
            main()

    def test_main_unsupported_extension(self, temp_dir: Path):
        """main() should exit with error for unsupported file type."""
        bad_file = temp_dir / "test.stl"
        bad_file.write_text("some content")

        with patch.object(sys, 'argv', ['3mf-analyzer', str(bad_file)]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1


# ═══════════════════════════════════════════════════════════════
# Test CLI combined flags for gcode
# ═══════════════════════════════════════════════════════════════

class TestGcodeCLICombinedFlags:
    """Test combined CLI flags for gcode files."""

    def test_main_gcode_combined_flags(self, sample_gcode: Path, capsys):
        """Multiple flags should work together for gcode files."""
        with patch.object(sys, 'argv', ['3mf-analyzer', str(sample_gcode), '--diff', '--wiki', '--no-color']):
            main()

        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_main_gcode_json_verbose(self, sample_gcode: Path, capsys):
        """--json and --verbose should work together for gcode."""
        with patch.object(sys, 'argv', ['3mf-analyzer', str(sample_gcode), '--json', '--verbose']):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert 'statistics' in data
        assert 'printer_model' in data['statistics']


# ═══════════════════════════════════════════════════════════════
# Test --update-wiki and --force-update-wiki flags
# ═══════════════════════════════════════════════════════════════

class TestWikiUpdateCLI:
    """Tests for --update-wiki and --force-update-wiki CLI flags."""

    def test_update_wiki_success(self):
        """--update-wiki should call wiki update and exit 0."""
        with patch.object(sys, 'argv', ['3mf-analyzer', '--update-wiki']), \
             patch('core.settings_wiki.update', return_value=True):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_update_wiki_already_up_to_date(self):
        """--update-wiki should handle 'already up to date' case."""
        with patch.object(sys, 'argv', ['3mf-analyzer', '--update-wiki']), \
             patch('core.settings_wiki.update', return_value=False):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_update_wiki_failure_exits_1(self):
        """--update-wiki should exit(1) if update raises an exception."""
        with patch.object(sys, 'argv', ['3mf-analyzer', '--update-wiki']), \
             patch('core.settings_wiki.update', side_effect=RuntimeError("Network error")):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1
