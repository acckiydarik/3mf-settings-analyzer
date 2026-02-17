#!/usr/bin/env python3
"""
3MF Settings Analyzer -- entry point.

Run directly:
    ./analyze.py model.3mf
    python analyze.py model.gcode --diff
"""

from analyzer.cli import main

if __name__ == "__main__":
    main()
