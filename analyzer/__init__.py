"""
3MF Settings Analyzer
Analyzes 3MF and Gcode files and displays slicer settings in a structured table format.
Supports Bambu Studio, OrcaSlicer, Snapmaker Orca, and other slicers using the same
3MF/Gcode metadata format.
"""

__version__ = "2.0.0"

from analyzer.threemf import ThreeMFAnalyzer
from analyzer.gcode import GcodeAnalyzer
from analyzer.output import print_results, print_gcode_results
from analyzer.cli import main, setup_logging

__all__ = [
    "__version__",
    "ThreeMFAnalyzer",
    "GcodeAnalyzer",
    "print_results",
    "print_gcode_results",
    "main",
    "setup_logging",
]
