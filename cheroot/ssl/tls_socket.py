"""
A unified SSL/TLS socket layer for Cheroot.

This module provides a TLSSocket class that abstracts over
different SSL/TLS implementations, such as Python's built-in ssl module
and pyOpenSSL. It offers a consistent interface for the rest of
the Cheroot server code.
"""

import errno
import io
import os
import socket
import ssl
import time
from contextlib import suppress

from .. import errors


try:
    from OpenSSL import SSL, crypto
except ImportError:
    SSL = None  # type: ignore[assignment]
    crypto = None  # type: ignore[assignment]
    ssl_conn_type = None  # type: ignore[misc]
else:
    # If the import succeeded, proceed with secondary checks
    # Use a separate try/except block for the connection type logic
    try:  # noqa: WPS505
        ssl_conn_type = SSL.Connection  # type: ignore[misc]
    except AttributeError:
        # Fallback to older name if 'Connection' is not found
        ssl_conn_type = SSL.ConnectionType  # type: ignore[attr-defined]

_OPENSSL_PROTOCOL_MAP = {
    769: 'TLSv1',
    770: 'TLSv1.1',
    771: 'TLSv1.2',
    772: 'TLSv1.2',
    773: 'TLSv1.3',
}


class TLSSocket(io.RawIOBase):  # noqa: PLR0904 # pylint: disable=too-many-public-methods
    """
    Lightweight wrapper around SSL/TLS sockets.

    Provides a uniform interface over both :class:`ssl.SSLSocket` and
    :class:`OpenSSL.SSL.Connection` objects, ensuring consistent I/O
    stream handling for Cheroot with proper SSL error handling.
    """

    def __init__(self, ssl_socket, raw_socket, context):
        """
        Initialize TLS socket wrapper.

        Args:
            ssl_socket: SSL/TLS wrapped socket (SSLSocket or pyOpenSSL Conn)
            raw_socket: The underlying raw socket
            context: The SSL context (SSLContext or pyOpenSSL Context)
        """
        self._ssl_socket = ssl_socket
        self._sock = raw_socket
        self.context = context
        self.ssl_retry = 0.01  # Retry interval for SSL errors
        self.ssl_retry_max = 0.1  # Maximum time to retry before timeout
        self._is_closed = False

        super().__init__()  # Initialize RawIOBase

    # ================================================================
    # Properties - delegate to underlying socket or return stored values
    # ================================================================

    @property
    def family(self):
        """Get socket family."""
        return getattr(self._sock, 'family', socket.AF_INET)

    @property
    def type(self):
        """Get socket type."""
        return getattr(self._sock, 'type', socket.SOCK_STREAM)

    @property
    def proto(self):
        """Get socket protocol."""
        return getattr(self._sock, 'proto', 0)

    @property
    def _closed(self):
        """Check if the connection is closed."""
        if self._sock is None:
            return True

        try:
            fd = self._sock.fileno()
            os.fstat(fd)
            return False
        except (OSError, AttributeError) as sockerr:
            if isinstance(sockerr, OSError) and sockerr.errno == errno.EBADF:
                return True
            return True

    @property
    def closed(self):
        """Public closed property."""
        return self._is_closed

    @property
    def scheme(self):
        """Signal to Cheroot that this is an HTTPS connection."""
        return 'https'

    # ================================================================
    # SSL Error Handling
    # ================================================================

    def _safe_call(self, is_reader, call, *args, **kwargs):  # noqa: C901
        r"""
        Wrap the given call with TLS error-trapping.

        This handles transient SSL errors like WantReadError and WantWriteError
        by retrying with a small sleep interval.
        """
        if not SSL:
            # If pyOpenSSL not available, just call directly
            return call(*args, **kwargs)

        start = time.time()

        while True:
            try:
                return call(*args, **kwargs)

            except SSL.WantReadError:
                # SSL needs more data to complete operation
                time.sleep(self.ssl_retry)
                if time.time() - start > self.ssl_retry_max:
                    raise socket.timeout('SSL WantReadError retry timeout')

            except SSL.WantWriteError:
                # SSL needs to write data before continuing
                time.sleep(self.ssl_retry)
                if time.time() - start > self.ssl_retry_max:
                    raise socket.timeout('SSL WantWriteError retry timeout')

            except SSL.SysCallError as sys_err:
                # System call error - check if it's ignorable
                if is_reader and sys_err.args == (-1, 'Unexpected EOF'):
                    return b''

                errnum = sys_err.args[0] if sys_err.args else -1
                if is_reader and errnum in errors.socket_errors_to_ignore:
                    return b''

                raise socket.error(errnum)

            except SSL.Error as ssl_err:
                # General SSL error - check for specific known errors
                if not ssl_err.args:
                    raise

                error_list = ssl_err.args[0]
                if not isinstance(error_list, list):
                    error_list = [error_list]

                for error_tuple in error_list:
                    if (
                        not isinstance(error_tuple, tuple)
                        or len(error_tuple) < 3
                    ):
                        continue

                    error_message = error_tuple[2].lower()

                    # HTTP request on HTTPS port
                    if 'http request' in error_message:
                        raise errors.NoSSLError

                    # Fatal SSL alert
                    if 'alert' in error_message:
                        raise errors.FatalSSLAlert(str(ssl_err))

                # Unknown SSL error
                raise

    # ================================================================
    # Socket I/O methods with error handling
    # ================================================================

    def readable(self):
        """Return True - this I/O object supports reading."""
        return True

    def writable(self):
        """Return True - this I/O object supports writing."""
        return True

    def seekable(self):
        """Return False - sockets are not seekable."""
        return False

    def recv(self, size):
        """Receive data from the connection with SSL error handling."""
        if SSL and isinstance(self._ssl_socket, ssl_conn_type):
            return self._safe_call(True, self._ssl_socket.recv, size)
        # For ssl.SSLSocket, just call recv directly
        # (it handles its own errors)
        return self._ssl_socket.recv(size)

    def send(self, data, flags=0):
        """Send data with SSL error handling."""
        if SSL and isinstance(self._ssl_socket, ssl_conn_type):
            return self._safe_call(False, self._ssl_socket.send, data, flags)
        return self._ssl_socket.send(data, flags)

    def sendall(self, data, flags=0):
        """Send all data with SSL error handling."""
        if SSL and isinstance(self._ssl_socket, ssl_conn_type):
            return self._safe_call(
                False,
                self._ssl_socket.sendall,
                data,
                flags,
            )
        return self._ssl_socket.sendall(data, flags)

    def readinto(self, buff):
        """
        Read data into a buffer - called by :class:`io.BufferedReader`.

        This is the key method that ``BufferedReader`` calls when reading.
        By implementing this with error handling, we ensure SSL errors
        are properly handled in the buffered I/O path.

        Args:
            buff: Buffer to read data into (bytearray or memoryview)

        Returns:
            Number of bytes read, or None for EOF
        """
        data = self.recv(len(buff))
        if not data:
            return 0  # EOF
        num_bytes = len(data)
        view = memoryview(buff)
        view[:num_bytes] = data
        return num_bytes

    def read(self, size):
        """Read data from the connection. Used by StreamReader."""
        return self.recv(size)

    def write(self, data):
        """Write data to the connection with SSL error handling."""
        return self.send(data)

    # ================================================================
    # Unified SSL/TLS methods - handle both backends
    # ================================================================

    def get_cipher_info(self):
        """
        Get the current cipher information in a unified format.

        Returns:
            tuple: (cipher_name, protocol_version, secret_bits) or None
        """
        ssl_socket = self._ssl_socket

        if isinstance(ssl_socket, ssl.SSLSocket):
            # Returns tuple: (cipher_name, protocol_version, secret_bits)
            return ssl_socket.cipher()

        if SSL and isinstance(ssl_socket, ssl_conn_type):
            try:
                protocol_constant = ssl_socket.get_protocol_version()
                protocol = _OPENSSL_PROTOCOL_MAP.get(
                    protocol_constant,
                    'UNKNOWN',
                )
                cipher_name = ssl_socket.get_cipher_name()
                active_bits = ssl_socket.get_cipher_bits()

                return (cipher_name, protocol, active_bits)

            except SSL.Error:
                return None
            except Exception as err:
                raise errors.FatalSSLAlert(
                    'Error retrieving cipher info from pyOpenSSL connection: '
                    + str(err),
                ) from err

        return None

    def getpeercert(self, binary_form=False):
        """
        Get the peer's certificate.

        Args:
            binary_form: If True, return DER-encoded bytes;
              else return dict/object

        Returns:
            Certificate in requested format, or None/empty dict if unavailable
        """
        if not hasattr(self, '_ssl_socket') or self._ssl_socket is None:
            return None if binary_form else {}

        # Handle PyOpenSSL Connection
        if SSL and isinstance(self._ssl_socket, ssl_conn_type):
            try:
                cert = self._ssl_socket.get_peer_certificate()
                if cert is None:
                    return None if binary_form else {}

                if binary_form:
                    return crypto.dump_certificate(crypto.FILETYPE_ASN1, cert)
                return cert
            except Exception:
                return None if binary_form else {}

        # Handle builtin ssl.SSLSocket
        return self._ssl_socket.getpeercert(binary_form)

    def get_verify_mode(self):
        """
        Get the certificate verification mode.

        Returns:
            int: ssl.CERT_NONE, ssl.CERT_OPTIONAL, or ssl.CERT_REQUIRED
        """
        ssl_socket = self._ssl_socket

        if isinstance(ssl_socket, ssl.SSLSocket):
            return ssl_socket.context.verify_mode

        if SSL and isinstance(ssl_socket, ssl_conn_type):
            verify_mode = self.context.get_verify_mode()

            # Map PyOpenSSL constants to ssl module constants
            if verify_mode == SSL.VERIFY_NONE:
                return ssl.CERT_NONE
            if verify_mode & SSL.VERIFY_PEER:
                # Check if cert is actually required or just optional
                if verify_mode & SSL.VERIFY_FAIL_IF_NO_PEER_CERT:
                    return ssl.CERT_REQUIRED  # Cert must be provided
                return ssl.CERT_OPTIONAL  # Cert requested but not required

        return ssl.CERT_NONE

    # ================================================================
    # Socket control methods - explicit delegation
    # ================================================================

    def fileno(self):
        """Return the file descriptor of the underlying socket."""
        if self._is_closed:
            raise ValueError('Socket is closed')
        if self._sock is None:
            raise ValueError('Socket is not initialized')

        fd = self._sock.fileno()
        if fd == -1:
            raise OSError('Socket has been closed')

        return fd

    def getpeername(self):
        """Return the address of the remote peer."""
        return self._sock.getpeername()

    def getsockname(self):
        """Return the address of the local machine."""
        return self._sock.getsockname()

    def gettimeout(self):
        """Get the timeout value."""
        return self._sock.gettimeout()

    def settimeout(self, timeout):
        """Set timeout on the connection."""
        return self._ssl_socket.settimeout(timeout)

    def setblocking(self, flag):
        """Set blocking mode."""
        return self._sock.setblocking(flag)

    def getsockopt(self, level, optname, buflen=None):
        """Get socket option."""
        if buflen is not None:
            return self._sock.getsockopt(level, optname, buflen)
        return self._sock.getsockopt(level, optname)

    def makefile(self, *args, **kwargs):
        """Create a file-like object from the connection."""
        return self._ssl_socket.makefile(*args, **kwargs)

    def shutdown(self, how):
        """Perform a clean SSL shutdown."""
        if isinstance(self._ssl_socket, ssl.SSLSocket):
            with suppress(Exception):
                self._ssl_socket.unwrap()

        with suppress(Exception):
            return self._sock.shutdown(how)

    def sock_shutdown(self, how):
        """Shutdown the raw socket (TCP level), bypassing SSL shutdown."""
        # Windows error code for "not a socket"
        WSAENOTSOCK = 10038
        try:
            # Attempt to shutdown the underlying kernel socket
            return self._sock.shutdown(how)
        except OSError as err:
            # errno 9 is EBADF (Bad file descriptor)
            if err.errno in {errno.EBADF, WSAENOTSOCK}:
                # The underlying socket was already closed,
                # which is fine during cleanup.
                # Silently ignore the error.
                return None
            # If it's another OSError, re-raise it.
            raise

    def close(self):
        """Close the connection."""
        if self._is_closed:
            return

        self._is_closed = True
        with suppress(Exception):
            self._ssl_socket.close()

    # ================================================================
    # Additional SSL methods that might be called
    # ================================================================

    def compression(self):
        """Get compression method (usually None for modern TLS)."""
        ssl_socket = self._ssl_socket
        if isinstance(ssl_socket, ssl.SSLSocket):
            return ssl_socket.compression()
        # pyOpenSSL doesn't support this easily, return None
        return None

    @property
    def sni(self):
        """Get SNI hostname if available."""
        ssl_socket = self._ssl_socket

        # SSLSocket doesn't expose SNI directly, return None
        if isinstance(ssl_socket, ssl.SSLSocket):
            return None

        # pyOpenSSL might have it via get_servername()
        if SSL and isinstance(ssl_socket, ssl_conn_type):
            with suppress(Exception):
                return ssl_socket.get_servername()
        return None

    def version(self):
        """Get TLS version."""
        ssl_socket = self._ssl_socket
        if isinstance(ssl_socket, ssl.SSLSocket):
            return ssl_socket.version()
        if SSL and isinstance(ssl_socket, ssl_conn_type):
            # Return string version
            protocol_constant = ssl_socket.get_protocol_version()
            return _OPENSSL_PROTOCOL_MAP.get(protocol_constant, 'UNKNOWN')
        return None

    def get_session(self):
        """Get SSL session for reuse (method form)."""
        ssl_socket = self._ssl_socket
        if isinstance(ssl_socket, ssl.SSLSocket):
            return ssl_socket.session  # Property on SSLSocket
        if SSL and isinstance(ssl_socket, ssl_conn_type):
            return ssl_socket.get_session()  # Method on pyOpenSSL
        return None

    @property
    def session(self):
        """Get SSL session for reuse."""
        ssl_socket = self._ssl_socket
        if isinstance(ssl_socket, ssl.SSLSocket):
            return ssl_socket.session
        if SSL and isinstance(ssl_socket, ssl_conn_type):
            return ssl_socket.get_session()
        return None
