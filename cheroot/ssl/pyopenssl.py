"""
A library for integrating :doc:`pyOpenSSL <pyopenssl:index>` with Cheroot.

The :py:mod:`OpenSSL <pyopenssl:OpenSSL>` module must be importable
for SSL/TLS/HTTPS functionality.
You can obtain it from `here <https://github.com/pyca/pyopenssl>`_.

To use this module, set :py:attr:`HTTPServer.ssl_adapter
<cheroot.server.HTTPServer.ssl_adapter>` to an instance of
:py:class:`ssl.Adapter <cheroot.ssl.Adapter>`.
There are two ways to use :abbr:`TLS (Transport-Level Security)`:

Method One
----------

 * :py:attr:`ssl_adapter.context
   <cheroot.ssl.pyopenssl.pyOpenSSLAdapter.context>`: an instance of
   :py:class:`SSL.Context <pyopenssl:OpenSSL.SSL.Context>`.

If this is not None, it is assumed to be an :py:class:`SSL.Context
<pyopenssl:OpenSSL.SSL.Context>` instance, and will be passed to
:py:class:`SSL.Connection <pyopenssl:OpenSSL.SSL.Connection>` on bind().
The developer is responsible for forming a valid :py:class:`Context
<pyopenssl:OpenSSL.SSL.Context>` object. This
approach is to be preferred for more flexibility, e.g. if the cert and
key are streams instead of files, or need decryption, or
:py:data:`SSL.SSLv3_METHOD <pyopenssl:OpenSSL.SSL.SSLv3_METHOD>`
is desired instead of the default :py:data:`SSL.SSLv23_METHOD
<pyopenssl:OpenSSL.SSL.SSLv3_METHOD>`, etc. Consult
the :doc:`pyOpenSSL <pyopenssl:api/ssl>` documentation for
complete options.

Method Two (shortcut)
---------------------

 * :py:attr:`ssl_adapter.certificate
   <cheroot.ssl.pyopenssl.pyOpenSSLAdapter.certificate>`: the file name
   of the server's TLS certificate.
 * :py:attr:`ssl_adapter.private_key
   <cheroot.ssl.pyopenssl.pyOpenSSLAdapter.private_key>`: the file name
   of the server's private key file.

Both are :py:data:`None` by default. If :py:attr:`ssl_adapter.context
<cheroot.ssl.pyopenssl.pyOpenSSLAdapter.context>` is :py:data:`None`,
but ``.private_key`` and ``.certificate`` are both given and valid, they
will be read, and the context will be automatically created from them.

.. spelling::

   pyopenssl
"""

import socket
import sys
import threading
import time
from warnings import warn as _warn


try:
    import OpenSSL.version
    from OpenSSL import (
        SSL,
        crypto,
    )

    try:
        ssl_conn_type = SSL.Connection
    except AttributeError:
        ssl_conn_type = SSL.ConnectionType
except ImportError:
    SSL = None
    ssl_conn_type = type(None)

import contextlib

from .. import (
    errors,
    server as cheroot_server,
)
from ..makefile import StreamReader, StreamWriter
from . import Adapter


class SSLFileobjectMixin:
    """Base mixin for a TLS socket stream."""

    ssl_timeout = 3
    ssl_retry = 0.01

    # FIXME:
    def _safe_call(self, is_reader, call, *args, **kwargs):  # noqa: C901
        """Wrap the given call with TLS error-trapping.

        is_reader: if False EOF errors will be raised. If True, EOF errors
        will return "" (to emulate normal sockets).
        """
        start = time.time()
        while True:
            try:
                return call(*args, **kwargs)
            except SSL.WantReadError:
                # Sleep and try again. This is dangerous, because it means
                # the rest of the stack has no way of differentiating
                # between a "new handshake" error and "client dropped".
                # Note this isn't an endless loop: there's a timeout below.
                # Ref: https://stackoverflow.com/a/5133568/595220
                time.sleep(self.ssl_retry)
            except SSL.WantWriteError:
                time.sleep(self.ssl_retry)
            except SSL.SysCallError as e:
                if is_reader and e.args == (-1, 'Unexpected EOF'):
                    return 0

                errnum = e.args[0]
                if is_reader and errnum in errors.socket_errors_to_ignore:
                    return 0
                raise socket.error(errnum)
            except SSL.Error as e:
                if is_reader and e.args == (-1, 'Unexpected EOF'):
                    return 0

                thirdarg = None
                with contextlib.suppress(IndexError):
                    thirdarg = e.args[0][0][2]

                if thirdarg == 'http request':
                    # The client is talking HTTP to an HTTPS server.
                    raise errors.NoSSLError

                raise errors.FatalSSLAlert(*e.args)

            if time.time() - start > self.ssl_timeout:
                raise socket.timeout('timed out')

    def sendall(self, *args, **kwargs):
        """Send whole message to the socket."""
        return self._safe_call(
            False,
            super(SSLFileobjectMixin, self).sendall,
            *args,
            **kwargs,
        )

    def send(self, *args, **kwargs):
        """Send some part of message to the socket."""
        return self._safe_call(
            False,
            super(SSLFileobjectMixin, self).send,
            *args,
            **kwargs,
        )


class SSLFileobjectStreamReader(SSLFileobjectMixin, StreamReader):
    """
    SSL file object attached to a socket object.

    .. deprecated::11.2
       This class is deprecated and will be removed in a future release.
    """

    def __init__(self, *args, **kwargs):
        """Initialize SSLFileobjectStreamReader."""
        _warn(
            '`SSLFileobjectStreamReader` and `SSLFileobjectStreamWriter` '
            'are deprecated. The `pyOpenSSL` adapter now returns `TLSSocket` '
            'which works directly with StreamReader/StreamWriter.',
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)


class SSLFileobjectStreamWriter(SSLFileobjectMixin, StreamWriter):
    """
    SSL file object attached to a socket object.

    .. deprecated::11.2
       This class is deprecated and will be removed in a future release.
    """

    def __init__(self, *args, **kwargs):
        """Initialize SSLFileobjectStreamWriter."""
        _warn(
            '`SSLFileobjectStreamReader` and `SSLFileobjectStreamWriter` '
            'are deprecated. The `pyOpenSSL` adapter now returns `TLSSocket` '
            'which works directly with StreamReader/StreamWriter.',
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)


class SSLConnectionProxyMeta:
    """Metaclass for generating a bunch of proxy methods."""

    def __new__(mcl, name, bases, nmspc):
        """Attach a list of proxy methods to a new class."""
        proxy_methods = (
            'get_context',
            'pending',
            'send',
            'write',
            'recv',
            'read',
            'renegotiate',
            'bind',
            'listen',
            'connect',
            'accept',
            'setblocking',
            'fileno',
            'close',
            'get_cipher_list',
            'getpeername',
            'getsockname',
            'getsockopt',
            'setsockopt',
            'makefile',
            'get_app_data',
            'set_app_data',
            'state_string',
            'sock_shutdown',
            'get_peer_certificate',
            'want_read',
            'want_write',
            'set_connect_state',
            'set_accept_state',
            'connect_ex',
            'sendall',
            'settimeout',
            'gettimeout',
            'shutdown',
            'recv_into',
            '_decref_socketios',
        )
        proxy_methods_no_args = ('shutdown',)

        proxy_props = ('family',)

        def lock_decorator(method):
            """Create a proxy method for a new class."""

            def proxy_wrapper(self, *args):
                self._lock.acquire()
                try:
                    new_args = (
                        args[:] if method not in proxy_methods_no_args else []
                    )
                    return getattr(self._ssl_conn, method)(*new_args)
                finally:
                    self._lock.release()

            return proxy_wrapper

        for m in proxy_methods:
            nmspc[m] = lock_decorator(m)
            nmspc[m].__name__ = m

        def make_property(property_):
            """Create a proxy method for a new class."""

            def proxy_prop_wrapper(self):
                return getattr(self._ssl_conn, property_)

            proxy_prop_wrapper.__name__ = property_
            return property(proxy_prop_wrapper)

        for p in proxy_props:
            nmspc[p] = make_property(p)

        # Doesn't work via super() for some reason.
        # Falling back to type() instead:
        return type(name, bases, nmspc)


class SSLConnection(metaclass=SSLConnectionProxyMeta):
    r"""A thread-safe wrapper for an ``SSL.Connection``.

    :param tuple args: the arguments to create the wrapped \
                        :py:class:`SSL.Connection(*args) \
                        <pyopenssl:OpenSSL.SSL.Connection>`
    """

    def __init__(self, *args):
        """Initialize ``SSLConnection`` instance."""
        self._ssl_conn = SSL.Connection(*args)
        self._lock = threading.RLock()

    @property
    def _socket(self):
        """
        Expose underlying raw socket.

        This is needed for times when the cheroot server needs access to the
        original socket object, e.g. in response to a client attempting
        to speak plain HTTP on an HTTPS port.
        """
        return self._ssl_conn._socket


class pyOpenSSLAdapter(Adapter):
    """A wrapper for integrating :doc:`pyOpenSSL <pyopenssl:index>`."""

    certificate = None
    """The file name of the server's TLS certificate."""

    private_key = None
    """The file name of the server's private key file."""

    certificate_chain = None
    """Optional. The file name of CA's intermediate certificate bundle.

    This is needed for cheaper "chained root" TLS certificates,
    and should be left as :py:data:`None` if not required."""

    context = None
    """
    An instance of :py:class:`SSL.Context <pyopenssl:OpenSSL.SSL.Context>`.
    """

    ciphers = None
    """The ciphers list of TLS."""

    private_key_password = None
    """Optional passphrase for password protected private key."""

    def __init__(
        self,
        certificate,
        private_key,
        certificate_chain=None,
        ciphers=None,
        *,
        private_key_password=None,
    ):
        """Initialize ``pyOpenSSLAdapter`` instance."""
        if SSL is None:
            raise ImportError('You must install pyOpenSSL to use HTTPS.')

        super(pyOpenSSLAdapter, self).__init__(
            certificate,
            private_key,
            certificate_chain,
            ciphers,
            private_key_password=private_key_password,
        )

        self.context = self.get_context()
        self._environ = self.get_environ()

    def wrap(self, sock):
        """Wrap and return the given socket, plus WSGI environ entries."""
        # pyOpenSSL doesn't perform the handshake until the first read/write
        # forcing the handshake to complete tends to result in the connection
        # closing so we can't reliably access protocol/client cert for the env

        sock, _env = super().wrap(  # checks for plaintext http on https port
            sock,
        )

        conn = SSLConnection(self.context, sock)
        conn.set_accept_state()  # Tell OpenSSL this is a server connection

        # Wrap the SSLConnection to provide standard socket interface
        tls_socket = _TLSSocket(underlying_socket=sock, tls_connection=conn)
        return tls_socket, self._environ.copy()

    def _password_callback(
        self,
        password_max_length,
        verify_twice,
        password_or_callback,
        /,
    ):
        """Pass a passphrase to password protected private key."""
        if callable(password_or_callback):
            password = password_or_callback()
            if verify_twice and password != password_or_callback():
                raise ValueError(
                    'Verification failed: entered passwords do not match',
                ) from None
        else:
            password = password_or_callback

        b_password = b''  # returning a falsy value communicates an error
        if isinstance(password, str):
            b_password = password.encode('utf-8')
        elif isinstance(password, bytes):
            b_password = password

        password_length = len(b_password)
        if password_length > password_max_length:
            _warn(
                f'User-provided password is {password_length} bytes long and will '
                f'be truncated since it exceeds the maximum of {password_max_length}.',
                UserWarning,
                stacklevel=1,
            )

        return b_password

    def get_context(self):
        """Return an ``SSL.Context`` from self attributes.

        Ref: :py:class:`SSL.Context <pyopenssl:OpenSSL.SSL.Context>`
        """
        # See https://code.activestate.com/recipes/442473/
        c = SSL.Context(SSL.SSLv23_METHOD)
        if self.private_key_password is None:
            self.private_key_password = self._prompt_for_tls_password
        c.set_passwd_cb(self._password_callback, self.private_key_password)
        c.use_privatekey_file(self.private_key)
        if self.certificate_chain:
            c.load_verify_locations(self.certificate_chain)
        c.use_certificate_file(self.certificate)
        return c

    def get_environ(self):
        """Return WSGI environ entries to be merged into each request."""
        ssl_environ = {
            'wsgi.url_scheme': 'https',
            'HTTPS': 'on',
            'SSL_VERSION_INTERFACE': '%s %s/%s Python/%s'
            % (
                cheroot_server.HTTPServer.version,
                OpenSSL.version.__title__,
                OpenSSL.version.__version__,
                sys.version,
            ),
            'SSL_VERSION_LIBRARY': SSL.SSLeay_version(
                SSL.SSLEAY_VERSION,
            ).decode(),
        }

        if self.certificate:
            # Server certificate attributes
            with open(self.certificate, 'rb') as cert_file:
                cert = crypto.load_certificate(
                    crypto.FILETYPE_PEM,
                    cert_file.read(),
                )

            ssl_environ.update(
                {
                    'SSL_SERVER_M_VERSION': cert.get_version(),
                    'SSL_SERVER_M_SERIAL': cert.get_serial_number(),
                    # 'SSL_SERVER_V_START':
                    #   Validity of server's certificate (start time),
                    # 'SSL_SERVER_V_END':
                    #   Validity of server's certificate (end time),
                },
            )

            for prefix, dn in [
                ('I', cert.get_issuer()),
                ('S', cert.get_subject()),
            ]:
                # X509Name objects don't seem to have a way to get the
                # complete DN string. Use str() and slice it instead,
                # because str(dn) == "<X509Name object '/C=US/ST=...'>"
                dnstr = str(dn)[18:-2]

                wsgikey = 'SSL_SERVER_%s_DN' % prefix
                ssl_environ[wsgikey] = dnstr

                # The DN should be of the form: /k1=v1/k2=v2, but we must allow
                # for any value to contain slashes itself (in a URL).
                while dnstr:
                    pos = dnstr.rfind('=')
                    dnstr, value = dnstr[:pos], dnstr[pos + 1 :]
                    pos = dnstr.rfind('/')
                    dnstr, key = dnstr[:pos], dnstr[pos + 1 :]
                    if key and value:
                        wsgikey = 'SSL_SERVER_%s_DN_%s' % (prefix, key)
                        ssl_environ[wsgikey] = value

        return ssl_environ

    def makefile(self, sock, mode='r', bufsize=-1):
        """
        Return socket file object.

        ``makefile`` is now deprecated and will be removed in a future
        version.
        """
        _warn(
            'The `makefile` method is deprecated and will be removed in a future version. '
            'The connection socket should be fully wrapped by the adapter '
            'before being passed to the HTTPConnection constructor.',
            DeprecationWarning,
            stacklevel=2,
        )

        return sock.makefile(mode, bufsize)


class _TLSSocket(SSLFileobjectMixin):
    """
    Wrap :py:class:`SSL.Connection <pyopenssl:OpenSSL.SSL.Connection>`.

    Wrapping with ``_TLSSocket`` makes it possible for an ``SSL.Connection``
    to work with :py:class:`~cheroot.makefile.StreamReader`/\
    :py:class:`~cheroot.makefile.StreamWriter`.

    ``_TLSSocket`` handles OpenSSL-specific errors by either
    suppressing them if they if they are acceptable during cleanup
    (e.g., "shutdown while in init", "uninitialized") or converting them to
    standard socket exceptions or Cheroot-specific errors (\
    :py:exc:`~cheroot.errors.FatalSSLAlert`,
    :py:exc:`~cheroot.errors.NoSSLError`) \
    for error handling by the calling I/O classes.
    """

    def __init__(
        self,
        underlying_socket,
        tls_connection,
        ssl_timeout=None,
        ssl_retry=0.01,
    ):
        """Initialize with an ``SSL.Connection`` object."""
        self._ssl_conn = tls_connection
        self._sock = underlying_socket  # Store reference to raw TCP socket
        self._lock = threading.RLock()
        self.ssl_timeout = ssl_timeout or 3.0
        self.ssl_retry = ssl_retry

    # Socket I/O
    # _safe_call is delegated to _TLSSockettMixin

    def recv_into(self, buffer, nbytes=None):
        """Receive data into a buffer."""
        with self._lock:
            return self._safe_call(
                True,
                self._ssl_conn.recv_into,
                buffer,
                nbytes,
            )

    def send(self, data):
        """Send data."""
        with self._lock:
            return self._safe_call(
                False,  # is_reader=False
                self._ssl_conn.send,
                data,
            )

    def fileno(self):
        """Return the file descriptor."""
        return self._ssl_conn.fileno()

    def _decref_socketios(self):
        """Decrement reference count for socket I/O streams.

        No-op for ``_TLSSocket`` since we don't track reference counts from
        :py:meth:`socket.socket.makefile() <python:socket.socket.makefile>`.
        The method is needed for compatibility with ``socket.SocketIO``,
        which is used by :py:class:`~cheroot.makefile.StreamReader` and
        :py:class:`~cheroot.makefile.StreamWriter`.
        """

    def shutdown(self, how):
        """Shutdown the connection.

        This is a no-op because actually for TLS sockets,
        true shutdown is handled by ``close()`` to ensure
        proper ordering (SSL shutdown before TCP shutdown).
        This method is kept for interface compatibility.
        """

    # C901 close is too complex
    def close(self):  # noqa: C901
        """Close the TLS socket and underlying connection."""
        exceptions = []

        # SSL errors that are acceptable during shutdown
        ACCEPTABLE_SSL_SHUTDOWN_ERRORS = {
            # Shutdown before handshake completed
            'shutdown while in init',
            'uninitialized',
        }

        acceptable_codes = errors.acceptable_sock_shutdown_error_codes

        # 1. Attempt an SSL-level shutdown
        try:
            self._ssl_conn.shutdown()
        except SSL.Error as e:
            # Many SSL shutdown errors expected when peer has already closed
            # SSL.ZeroReturnError means clean shutdown
            if isinstance(e, SSL.ZeroReturnError):
                pass  # Clean shutdown, not an error
            elif isinstance(e, SSL.SysCallError):
                # Check if it's a syscall error with an acceptable errno
                if e.args:
                    errno_code = e.args[0]
                    if errno_code not in acceptable_codes:
                        exceptions.append(e)
            else:
                # Check the OpenSSL error reason code
                error_reason = None
                if hasattr(e, '_reason_code'):
                    error_reason = e._reason_code
                elif e.args:
                    # PyOpenSSL Error format: ([('SSL routines', '', 'reason_string')],)
                    # Note: e.args[0] is a LIST of tuples, not a tuple itself
                    error_list = e.args[0] if e.args else []
                    for err_tuple in error_list:
                        if (
                            isinstance(err_tuple, tuple)
                            and len(err_tuple) >= 3
                        ):
                            error_reason = err_tuple[2]
                            break

                if error_reason not in ACCEPTABLE_SSL_SHUTDOWN_ERRORS:
                    exceptions.append(e)
        except OSError as e:
            if e.errno not in acceptable_codes:
                exceptions.append(e)

        # 2. Close the raw TCP socket
        try:
            self._sock.close()
        except OSError as e:
            if e.errno not in acceptable_codes:
                exceptions.append(e)

        # Re-raise collected exceptions as Cheroot-compatible errors
        if exceptions:
            if len(exceptions) == 1:
                exc = exceptions[0]
                raise errors.FatalSSLAlert(
                    f'Error during TLS socket close: {type(exc).__name__}: {exc}',
                ) from exc
            # Multiple errors - combine into single message
            error_msgs = [f'{type(e).__name__}: {e}' for e in exceptions]
            combined_errors = '; '.join(error_msgs)
            raise errors.FatalSSLAlert(
                f'Multiple errors during close: {combined_errors}',
            ) from exceptions[0]
