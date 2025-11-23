"""Implementation of the SSL adapter base interface."""

import socket
from abc import ABC, abstractmethod


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

    @abstractmethod
    def bind(self, sock):
        """Wrap and return the given socket."""
        return sock

    @abstractmethod
    def wrap(self, sock):
        """Wrap and return the given socket, plus WSGI environ entries."""
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    def get_environ(self):
        """Return WSGI environ entries to be merged into each request."""
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    def makefile(self, sock, mode='r', bufsize=-1):
        """Return socket file object."""
        raise NotImplementedError  # pragma: no cover

    def _check_for_plain_http(self, raw_socket):
        """Check if the client sent plain HTTP by peeking at first bytes.

        This is a best-effort check to provide a helpful error message when
        clients accidentally use HTTP on an HTTPS port. If we can't detect
        plain HTTP (timeout, no data yet, etc), we return False and let the
        SSL handshake proceed, which will fail with its own error.

        Returns:
            bool: True if plain HTTP is detected, False otherwise
        """
        PEEK_BYTES = 16
        PEEK_TIMEOUT = 0.5

        original_timeout = raw_socket.gettimeout()
        raw_socket.settimeout(PEEK_TIMEOUT)

        try:
            first_bytes = raw_socket.recv(PEEK_BYTES, socket.MSG_PEEK)
        except (OSError, socket.timeout):
            return False
        finally:
            raw_socket.settimeout(original_timeout)

        if not first_bytes:
            return False

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
        return first_bytes.startswith(http_methods)
