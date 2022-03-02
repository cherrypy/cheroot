"""High-performance, pure-Python HTTP server used by CherryPy."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

try:
    from importlib.metadata import version
except ImportError:
    try:
        from importlib_metadata import version
    except ImportError:
        pass


try:
    __version__ = version('cheroot')
except Exception:
    __version__ = 'unknown'
