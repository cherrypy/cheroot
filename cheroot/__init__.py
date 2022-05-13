"""High-performance, pure-Python HTTP server used by CherryPy."""

from __future__ import absolute_import, division, print_function
import re
__metaclass__ = type

try:
    import pkg_resources
except ImportError:
    pass


try:
    __version__ = re.search(
        r'(?x)^(\d+)\.(\d+)(\.(\d+))?([ab](\d+))?',
        pkg_resources.get_distribution('cheroot').version,
    ).expand(r'\1.\2\3\5')
except Exception:
    __version__ = 'unknown'
