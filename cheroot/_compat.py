"""Compatibility code for using Cheroot with various versions of Python.

Cheroot is compatible with Python versions 2.6+. This module provides a
useful abstraction over the differences between Python versions, sometimes by
preferring a newer idiom, sometimes an older one, and sometimes a custom one.
In particular, Python 2 uses str and '' for byte strings, while Python 3
uses str and '' for unicode strings. Refer to each of these the 'native
string' type for each version. Because of this major difference, this module
provides
'ntou', which translates native
strings to unicode strings. This also provides a 'BytesIO' name for dealing
specifically with bytes, and a 'StringIO' name for dealing with native strings.
It also provides a 'base64_decode' function with native strings as input and
output.
"""

import re

import six
from six.moves import urllib

if six.PY3:
    def ntou(n, encoding='ISO-8859-1'):
        """Return the given native string as a unicode string with the given encoding."""
        assert_native(n)
        # In Python 3, the native string type is unicode
        return n

    def tonative(n, encoding='ISO-8859-1'):
        """Return the given string as a native string in the given encoding."""
        # In Python 3, the native string type is unicode
        if isinstance(n, bytes):
            return n.decode(encoding)
        return n

    def bton(b, encoding='ISO-8859-1'):
        """Return the given byte string as a native string in the given encoding."""
        return b.decode(encoding)
else:
    # Python 2

    def ntou(n, encoding='ISO-8859-1'):
        """Return the given native string as a unicode string with the given encoding."""
        assert_native(n)
        # In Python 2, the native string type is bytes.
        # First, check for the special encoding 'escape'. The test suite uses
        # this to signal that it wants to pass a string with embedded \uXXXX
        # escapes, but without having to prefix it with u'' for Python 2,
        # but no prefix for Python 3.
        if encoding == 'escape':
            return six.u(
                re.sub(r'\\u([0-9a-zA-Z]{4})',
                       lambda m: six.unichr(int(m.group(1), 16)),
                       n.decode('ISO-8859-1')))
        # Assume it's already in the given encoding, which for ISO-8859-1
        # is almost always what was intended.
        return n.decode(encoding)

    def tonative(n, encoding='ISO-8859-1'):
        """Return the given string as a native string in the given encoding."""
        # In Python 2, the native string type is bytes.
        if isinstance(n, six.text_type):
            return n.encode(encoding)
        return n

    def bton(b, encoding='ISO-8859-1'):
        """Return the given byte string as a native string in the given encoding."""
        return b


def assert_native(n):
    """Check whether the input is of nativ ``str`` type.

    Raises:
        TypeError: in case of failed check
    """
    if not isinstance(n, str):
        raise TypeError('n must be a native str (got %s)' % type(n).__name__)


from six.moves.urllib.parse import (  # noqa: F401
    urlencode, urljoin, unquote_to_bytes,
)
from six.moves.urllib.request import (  # noqa: F401
    urlopen, parse_http_list, parse_keqv_list,
)

if six.PY3:
    def unquote_qs(atom, encoding, errors='strict'):
        """Return urldecoded query string."""
        return urllib.parse.unquote(
            atom.replace('+', ' '),
            encoding=encoding,
            errors=errors,
        )
else:
    def unquote_qs(atom, encoding, errors='strict'):
        """Return urldecoded query string."""
        return urllib.parse.unquote(
            atom.replace('+', ' '),
        ).decode(encoding, errors)

text_or_bytes = six.text_type, six.binary_type

# html module come in 3.2 version
try:
    from html import escape
except ImportError:
    from cgi import escape


# html module needed the argument quote=False because in cgi the default
# is False. With quote=True the results differ.

def escape_html(s, escape_quote=False):
    """Replace special characters "&", "<" and ">" to HTML-safe sequences.

    When escape_quote=True, escape (') and (") chars.
    """
    return escape(s, quote=escape_quote)
