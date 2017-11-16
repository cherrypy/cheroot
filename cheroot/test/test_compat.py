"""Test Python 2/3 compatibility module."""
from __future__ import unicode_literals

import unittest

from cheroot import _compat as compat


class EscapeTester(unittest.TestCase):
    """Class to test escape_html function from _cpcompat."""

    def test_escape_quote(self):
        """Verify the output for &<>"' chars."""
        self.assertEqual("""xx&amp;&lt;&gt;"aa'""", compat.escape_html("""xx&<>"aa'"""))
