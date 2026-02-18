"""Single source of truth for the package version.

Kept in a separate module so that setuptools can read it via
``version = {attr = "core._version.__version__"}`` without triggering
heavy imports from __init__.py (rich, defusedxml, etc.).
"""

__version__ = "2.4.2"
