"""
3MF Settings Analyzer
Analyzes 3MF and Gcode files and displays slicer settings in a structured table format.
Supports Bambu Studio, OrcaSlicer, Snapmaker Orca, and other slicers using the same
3MF/Gcode metadata format.
"""

__version__ = "2.1.2"

from core.threemf import ThreeMFAnalyzer
from core.gcode import GcodeAnalyzer
from core.output import print_results, print_gcode_results
from core.compare import print_gcode_comparison, print_3mf_comparison
from core.cli import main, setup_logging

__all__ = [
    "__version__",
    "ThreeMFAnalyzer",
    "GcodeAnalyzer",
    "print_results",
    "print_gcode_results",
    "print_gcode_comparison",
    "print_3mf_comparison",
    "main",
    "setup_logging",
]
