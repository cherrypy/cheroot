"""Compatibility code for using Cheroot with various versions of Python.

Cheroot 4 is compatible with Python versions 2.3+. This module provides a
useful abstraction over the differences between Python versions, sometimes by
preferring a newer idiom, sometimes an older one, and sometimes a custom one.

In particular, Python 2 uses str and '' for byte strings, while Python 3
uses str and '' for unicode strings. We will call each of these the 'native
string' type for each version. Because of this major difference, this module
provides new 'bytestr', 'unicodestr', and 'nativestr' attributes, as well as
two functions: 'ntob', which translates native strings (of type 'str'
regardless of Python version) into byte strings, and 'ntou', which translates
native strings to unicode strings.
"""
import os
import re
import sys

if sys.version_info >= (3, 0):
    py3k = True
    bytestr = bytes
    unicodestr = str
    nativestr = unicodestr
    basestring = (bytes, str)
    def ntob(n, encoding='ISO-8859-1'):
        """Return the given native string as a byte string in the given encoding."""
        # In Python 3, the native string type is unicode
        return n.encode(encoding)
    def ntou(n, encoding='ISO-8859-1'):
        """Return the given native string as a unicode string with the given encoding."""
        # In Python 3, the native string type is unicode
        return n
    def tonative(n, encoding='ISO-8859-1'):
        """Return the given string as a native string in the given encoding."""
        # In Python 3, the native string type is unicode
        if isinstance(n, bytes):
            return n.decode(encoding)
        return n
    # type("")
    from io import StringIO
    # bytes:
    from io import BytesIO as BytesIO
else:
    # Python 2
    py3k = False
    bytestr = str
    unicodestr = unicode
    nativestr = bytestr
    basestring = basestring
    def ntob(n, encoding='ISO-8859-1'):
        """Return the given native string as a byte string in the given encoding."""
        # In Python 2, the native string type is bytes. Assume it's already
        # in the given encoding, which for ISO-8859-1 is almost always what
        # was intended.
        return n
    def ntou(n, encoding='ISO-8859-1'):
        """Return the given native string as a unicode string with the given encoding."""
        # In Python 2, the native string type is bytes.
        # First, check for the special encoding 'escape'. The test suite uses this
        # to signal that it wants to pass a string with embedded \uXXXX escapes,
        # but without having to prefix it with u'' for Python 2, but no prefix
        # for Python 3.
        if encoding == 'escape':
            return unicode(
                re.sub(r'\\u([0-9a-zA-Z]{4})',
                       lambda m: unichr(int(m.group(1), 16)),
                       n.decode('ISO-8859-1')))
        # Assume it's already in the given encoding, which for ISO-8859-1 is almost
        # always what was intended.
        return n.decode(encoding)
    def tonative(n, encoding='ISO-8859-1'):
        """Return the given string as a native string in the given encoding."""
        # In Python 2, the native string type is bytes.
        if isinstance(n, unicode):
            return n.encode(encoding)
        return n
    try:
        # type("")
        from cStringIO import StringIO
    except ImportError:
        # type("")
        from StringIO import StringIO
    # bytes:
    BytesIO = StringIO

try:
    set = set
except NameError:
    from sets import Set as set

if py3k:
    from urllib.request import urlopen
    PERCENT = ntob('%')
    EMPTY = ntob('')
    def unquote(path):
        """takes quoted byte string and unquotes % encoded values""" 
        res = path.split(PERCENT)
        for i in range(1, len(res)):
            item = res[i]
            res[i] = bytes([int(item[:2], 16)]) + item[2:]
        return EMPTY.join(res)
else:
    from urllib import urlopen
    from urllib import unquote

try:
    # Python 2.
    from httplib import BadStatusLine, HTTPConnection, IncompleteRead, NotConnected
    from BaseHTTPServer import BaseHTTPRequestHandler
except ImportError:
    # Python 3
    from http.client import BadStatusLine, HTTPConnection, IncompleteRead, NotConnected
    from http.server import BaseHTTPRequestHandler

try:
    # Python 2.
    from httplib import HTTPSConnection
except ImportError:
    try:
        # Python 3
        from http.client import HTTPSConnection
    except ImportError:
        # Some platforms which don't have SSL don't expose HTTPSConnection
        HTTPSConnection = None

try:
    from email.utils import formatdate
    def HTTPDate(timeval=None):
        return formatdate(timeval, usegmt=True).encode('ISO-8859-1')
except ImportError:
    from rfc822 import formatdate as HTTPDate

try:
    # Python 2.4+
    from traceback import format_exc
except ImportError:
    import traceback
    def format_exc(limit=None):
        """Like print_exc() but return a string. Backport for Python 2.3."""
        try:
            etype, value, tb = sys.exc_info()
            return ''.join(traceback.format_exception(etype, value, tb, limit))
        finally:
            etype = value = tb = None


