#!/usr/bin/env python3
"""
3MF Settings Analyzer -- entry point.

Run directly:
    ./3mf_analyzer.py model.3mf
    python3 3mf_analyzer.py model.gcode --diff
"""

from core.cli import main

if __name__ == "__main__":
    main()
