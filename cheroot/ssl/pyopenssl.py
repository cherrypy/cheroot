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

 * ``ssl_adapter.context``: an instance of
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

Both are :py:data:`None` by default. If ``ssl_adapter.context``
is :py:data:`None`, but ``.private_key`` and ``.certificate`` are both
given and valid, they will be read, and the context will be automatically
created from them.

.. spelling::

   pyopenssl
"""

import select
import sys
from contextlib import suppress
from warnings import warn as _warn

from . import Adapter, parse_pyopenssl_cert_to_environ
from .tls_socket import TLSSocket


try:
    import OpenSSL.version
    from OpenSSL import SSL, crypto

    try:
        ssl_conn_type = SSL.Connection
    except AttributeError:
        ssl_conn_type = SSL.ConnectionType
except ImportError:
    SSL = None
    crypto = None

from .. import errors
from ..makefile import StreamReader, StreamWriter


class SSLFileobjectStreamReader(StreamReader):
    """SSL file object attached to a socket object."""


class SSLFileobjectStreamWriter(StreamWriter):
    """SSL file object attached to a socket object."""


class pyOpenSSLAdapter(Adapter):  # noqa: WPS214
    """A wrapper for integrating :doc:`pyOpenSSL <pyopenssl:index>`."""

    certificate = None
    """The file name of the server's TLS certificate."""

    private_key = None
    """The file name of the server's private key file."""

    certificate_chain = None
    """Optional. The file name of CA's intermediate certificate bundle.

    This is needed for cheaper "chained root" TLS certificates,
    and should be left as :py:data:`None` if not required."""

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
        """Initialize OpenSSL Adapter instance."""
        if SSL is None:
            raise ImportError('You must install pyOpenSSL to use HTTPS.')

        super().__init__(
            certificate,
            private_key,
            certificate_chain,
            ciphers,
            private_key_password=private_key_password,
        )
        self._environ = None
        self.context = None

    def bind(self, sock):
        """
        Prepare the server socket.

        Ensures that the SSL context object is created
        and fully configured. For Method One the caller
        supplies the context at ``__init()__`` but for
        Method Two we construct from certificate files.
        """
        if self._context is None:
            # Method Two
            _ = self.context  # triggers initialization via property
        return sock

    def wrap(self, sock):
        """Wrap client socket with SSL and return environ entries."""
        tls_socket = self._wrap_with_pyopenssl(sock)
        ssl_environ = self.get_environ(tls_socket)
        return tls_socket, ssl_environ

    def _wrap_with_pyopenssl(self, raw_socket, server_side=True):
        """Create a TLSSocket wrapping a PyOpenSSL connection."""
        pyopenssl_ssl_object = self._create_pyopenssl_connection(raw_socket)
        self._configure_connection_state(pyopenssl_ssl_object, server_side)
        self._perform_handshake(pyopenssl_ssl_object, raw_socket)

        # lgtm[py/insecure-protocol]
        return TLSSocket(
            ssl_socket=pyopenssl_ssl_object,
            raw_socket=raw_socket,
            context=self.context,
        )

    def _create_pyopenssl_connection(self, raw_socket):
        """Create PyOpenSSL connection object."""
        try:
            ssl_object = ssl_conn_type(self.context, raw_socket)
        except SSL.Error as e:
            raise errors.FatalSSLAlert(
                f'Error creating pyOpenSSL connection: {e}',
            ) from e

        ssl_object.setblocking(True)
        return ssl_object

    def _configure_connection_state(self, ssl_object, server_side):
        """Set connection to server or client mode."""
        if server_side:
            ssl_object.set_accept_state()
        else:
            ssl_object.set_connect_state()

    def _perform_handshake(self, ssl_object, raw_socket):
        """Perform SSL handshake with error handling."""
        while True:
            try:
                ssl_object.do_handshake()
                return
            except SSL.WantReadError:
                self._wait_for_handshake_data(raw_socket)
            except SSL.ZeroReturnError as e:
                raise errors.NoSSLError(
                    'Peer closed connection during handshake.',
                ) from e
            except SSL.Error as e:
                self._handle_ssl_error(e)
            except OSError as e:
                raise errors.FatalSSLAlert(
                    f'TCP error during handshake: {e}',
                ) from e

    def _wait_for_handshake_data(self, raw_socket):
        """Wait for peer to send data during handshake."""
        HANDSHAKE_TIMEOUT = 5.0
        fileno = raw_socket.fileno()
        ready_to_read, _, _ = select.select(
            [fileno],
            [],
            [],
            HANDSHAKE_TIMEOUT,
        )

        if not ready_to_read:
            raise TimeoutError(
                'Handshake failed: Peer did not send expected data.',
            )

    def _handle_ssl_error(self, error):
        """Handle SSL errors during handshake."""
        err_str = str(error)
        if 'http request' in err_str:
            raise errors.NoSSLError(
                'Client sent plain HTTP request',
            ) from error
        raise errors.FatalSSLAlert(
            f'Fatal SSL error during handshake: {err_str}',
        ) from error

    @property
    def context(self):
        """Get the SSL context."""
        if self._context is None:
            # Method Two: auto-create from certificate/private_key
            self._context = self.get_context()
        return self._context

    @context.setter
    def context(self, value):
        """Set the SSL context (Method One)."""
        self._context = value

    def get_context(self):
        """Return an SSL.Context from self attributes.

        Uses TLS_SERVER_METHOD which supports TLS 1.0-1.3, but immediately
        disables insecure protocols (SSLv2, SSLv3, TLSv1.0, TLSv1.1) via
        set_options(), ensuring only TLS 1.2+ is accepted.
        """
        c = SSL.Context(SSL.TLS_SERVER_METHOD)  # nosec B502

        # Disable all insecure protocols (SSLv2, SSLv3, TLSv1.0, TLSv1.1)
        c.set_options(
            SSL.OP_NO_SSLv2
            | SSL.OP_NO_SSLv3
            | SSL.OP_NO_TLSv1
            | SSL.OP_NO_TLSv1_1,
        )

        c.set_passwd_cb(self._password_callback, self.private_key_password)
        c.use_privatekey_file(self.private_key)
        if self.certificate_chain:
            c.load_verify_locations(self.certificate_chain)
        c.use_certificate_file(self.certificate)
        return c

    def _password_callback(
        self,
        password_max_length,
        _verify_twice,
        password,
        /,
    ):
        """Pass a passphrase to password protected private key."""
        b_password = b''
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

    # ========================================================================
    # Adapter-specific environment variable methods
    # ========================================================================

    def _get_library_version_environ(self):
        """Get SSL library version information for pyOpenSSL."""
        return {
            'SSL_VERSION_INTERFACE': '%s %s/%s Python/%s'
            % (
                'Cheroot',
                OpenSSL.version.__title__,
                OpenSSL.version.__version__,
                sys.version,
            ),
            'SSL_VERSION_LIBRARY': SSL.OpenSSL_version(
                SSL.OPENSSL_VERSION,
            ).decode('ascii'),
        }

    def _get_optional_environ(self, conn):
        """Get optional environment variables for pyOpenSSL."""
        # pyOpenSSL doesn't easily expose SNI or compression info
        # Could be extended in the future
        return {}

    def _get_server_cert_environ(self):
        """Get server certificate info using pyOpenSSL certificate parsing."""
        if not self.certificate or crypto is None:
            return {}

        try:
            with open(self.certificate, 'rb') as cert_file:
                cert_data = cert_file.read()

            cert = crypto.load_certificate(crypto.FILETYPE_PEM, cert_data)
            return parse_pyopenssl_cert_to_environ(cert, 'SSL_SERVER')

        except Exception:
            # If certificate parsing fails, return empty dict
            return {}

    def _get_client_cert_environ(self, conn, ssl_environ):
        """Add client certificate details using pyOpenSSL."""
        with suppress(Exception):
            # Get the peer certificate from the pyOpenSSL connection
            # conn is a TLSSocket, so we need to access the
            # underlying SSL socket
            ssl_socket = conn._ssl_socket

            # Check if peer verification was enabled
            if ssl_socket.get_context().get_verify_mode() == SSL.VERIFY_NONE:
                return ssl_environ

            client_cert = ssl_socket.get_peer_certificate()

            if client_cert:
                ssl_environ['SSL_CLIENT_VERIFY'] = 'SUCCESS'
                ssl_environ.update(
                    parse_pyopenssl_cert_to_environ(
                        client_cert,
                        'SSL_CLIENT',
                    ),
                )

                # Get PEM representation of certificate
                pem_cert = (
                    crypto.dump_certificate(
                        crypto.FILETYPE_PEM,
                        client_cert,
                    )
                    .decode('ascii')
                    .strip()
                )
                ssl_environ['SSL_CLIENT_CERT'] = pem_cert

        return ssl_environ
