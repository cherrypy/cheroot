"""High-performance, pure-Python HTTP server used by CherryPy."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

try:
    from importlib import metadata
except ImportError:
    import importlib_metadata as metadata  # noqa: WPS440


try:
    __version__ = metadata.version('cheroot')
except Exception:
    __version__ = 'unknown'
