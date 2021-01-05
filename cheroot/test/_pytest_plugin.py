"""Local pytest plugin.

Contains hooks, which are tightly bound to the Cheroot framework
itself, useless for end-users' app testing.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

from pytest import __version__


pytest_version = tuple(map(int, __version__.split('.')))
unraisable_exceptions = {
    ('pytest', 'PytestUnhandledThreadExceptionWarning'),
    ('pytest', 'PytestUnraisableExceptionWarning'),
}


def pytest_load_initial_conftests(early_config, parser, args):
    """Drop unfilterable warning ignores."""
    if pytest_version >= (6, 2, 0):
        return

    early_config._inicache['filterwarnings'] = [
        fw for fw in early_config.getini('filterwarnings')
        if fw.count(':') < 2 or
        tuple(fw.split(':')[2].split('.')[:2]) not in unraisable_exceptions
    ]
