import sys

from cheroot.compat import basestring, py3k

DEFAULT_BUFFER_SIZE = -1


class SSLAdapter(object):
    """Base class for SSL driver library adapters.

    Required methods:

        * ``wrap(sock) -> (wrapped socket, ssl environ dict)``
        * ``makefile(sock, mode='r', bufsize=DEFAULT_BUFFER_SIZE) ->
          socket file object``
    """

    def __init__(self, certificate, private_key, certificate_chain=None):
        self.certificate = certificate
        self.private_key = private_key
        self.certificate_chain = certificate_chain

    def wrap(self, sock):
        raise NotImplemented

    def makefile(self, sock, mode='r', bufsize=DEFAULT_BUFFER_SIZE):
        raise NotImplemented


# These may either be SSLAdapter subclasses or the string names
# of such classes (in which case they will be lazily loaded).
ssl_adapters = {
    'builtin': 'cheroot.ssllib.ssl_builtin.BuiltinSSLAdapter',
    'pyopenssl': 'cheroot.ssllib.ssl_pyopenssl.pyOpenSSLAdapter',
}


def get_ssl_adapter_class(name=None):
    """Return an SSL adapter class for the given name."""
    if name is None:
        if py3k:
            name = 'builtin'
        else:
            name = 'pyopenssl'

    adapter = ssl_adapters[name.lower()]
    if isinstance(adapter, basestring):
        last_dot = adapter.rfind(".")
        attr_name = adapter[last_dot + 1:]
        mod_path = adapter[:last_dot]

        try:
            mod = sys.modules[mod_path]
            if mod is None:
                raise KeyError()
        except KeyError:
            # The last [''] is important.
            mod = __import__(mod_path, globals(), locals(), [''])

        # Let an AttributeError propagate outward.
        try:
            adapter = getattr(mod, attr_name)
        except AttributeError:
            raise AttributeError("'%s' object has no attribute '%s'"
                                 % (mod_path, attr_name))

    return adapter
