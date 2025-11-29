"""Implementation of the SSL adapter base interface."""

import socket as _socket
from abc import ABC, abstractmethod
from warnings import warn as _warn

from .. import errors


class Adapter(ABC):
    """Base class for SSL driver library adapters.

    Required methods:

        * ``wrap(sock) -> (wrapped socket, ssl environ dict)``
        * ``makefile(sock, mode='r', bufsize=DEFAULT_BUFFER_SIZE) ->
          socket file object``
    """

    @abstractmethod
    def __init__(
        self,
        certificate,
        private_key,
        certificate_chain=None,
        ciphers=None,
        *,
        private_key_password=None,
    ):
        """Set up certificates, private key, ciphers and reset context."""
        self.certificate = certificate
        self.private_key = private_key
        self.certificate_chain = certificate_chain
        self.ciphers = ciphers
        self.private_key_password = private_key_password
        self.context = None

    def bind(self, sock):
        """
        Return the given socket.

        Deprecated:
        This method no longer performs any SSL-specific operations.
        SSL wrapping now happens in :meth:`.wrap`. :meth:`.bind` will be
        removed in a future version.
        """
        _warn(
            'SSLAdapter.bind() is deprecated and will be removed in a future version.',
            DeprecationWarning,
            stacklevel=2,
        )
        return sock

    def wrap(self, sock):
        """Wrap the given socket and return WSGI environ entries."""
        self._ensure_peer_speaks_https(sock)

    @abstractmethod
    def get_environ(self):
        """Return WSGI environ entries to be merged into each request."""
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    def makefile(self, sock, mode='r', bufsize=-1):
        """Return socket file object."""
        raise NotImplementedError  # pragma: no cover

    def _ensure_peer_speaks_https(self, raw_socket) -> None:
        """
        Raise exception if the client sent plain HTTP.

        Check if client sent HTTP on an HTTPS port by peeking at the
        first bytes. If there's no data yet we return and let the
        SSL handshake proceed, which which will raise an SSLError
        if the client is not speaking TLS.

        :raises NoSSLError: When plain HTTP is detected on an HTTPS socket
        """
        PEEK_BYTES = 16
        PEEK_TIMEOUT = 0.5

        original_timeout = raw_socket.gettimeout()
        raw_socket.settimeout(PEEK_TIMEOUT)

        try:
            first_bytes = raw_socket.recv(PEEK_BYTES, _socket.MSG_PEEK)
        except (OSError, _socket.timeout):
            return
        finally:
            raw_socket.settimeout(original_timeout)

        if not first_bytes:
            return

        http_methods = (
            b'GET ',
            b'POST ',
            b'PUT ',
            b'DELETE ',
            b'HEAD ',
            b'OPTIONS ',
            b'PATCH ',
            b'CONNECT ',
            b'TRACE ',
        )
        if first_bytes.startswith(http_methods):
            raise errors.NoSSLError(
                'Expected HTTPS on the socket but got plain HTTP',
            ) from None
