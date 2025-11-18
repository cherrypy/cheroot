"""Implementation of the SSL adapter base interface.

.. spelling::
   dn
"""

from abc import ABC, abstractmethod
from contextlib import suppress


DN_SEPARATOR = '/'  # Distinguished Name separator
UTF8_ENCODING = 'utf-8'


def _parse_dn_components(components, key_prefix, dn_type):
    """
    Parse Distinguished Name components into environ dict.

    Args:
        components: Iterable of (key, value) tuples
        key_prefix: 'SSL_CLIENT' or 'SSL_SERVER'
        dn_type: 'S' for subject or 'I' for issuer

    Returns:
        dict: ``DN`` and ``CN`` environment variables
    """
    env = {}
    dn_parts = []

    for key, attr_value in components:
        dn_parts.append(f'{key}={attr_value}')
        if key in {'CN', 'commonName'}:
            env[f'{key_prefix}_{dn_type}_DN_CN'] = attr_value

    if dn_parts:
        dn_string = DN_SEPARATOR.join(dn_parts)
        env[f'{key_prefix}_{dn_type}_DN'] = f'{DN_SEPARATOR}{dn_string}'

    return env


def parse_pyopenssl_cert_to_environ(cert, key_prefix):
    """Parse a pyOpenSSL X509 certificate into WSGI environ dict."""
    env = {}
    if not cert:
        return env

    # Subject
    subject = cert.get_subject()
    if subject:
        components = [
            (key.decode(UTF8_ENCODING), attr_value.decode(UTF8_ENCODING))
            for key, attr_value in subject.get_components()
        ]
        env.update(_parse_dn_components(components, key_prefix, 'S'))

    # Issuer
    issuer = cert.get_issuer()
    if issuer:
        components = [
            (key.decode(UTF8_ENCODING), attr_value.decode(UTF8_ENCODING))
            for key, attr_value in issuer.get_components()
        ]
        env.update(_parse_dn_components(components, key_prefix, 'I'))

    # Version and Serial
    env[f'{key_prefix}_M_VERSION'] = str(cert.get_version())
    env[f'{key_prefix}_M_SERIAL'] = str(cert.get_serial_number())

    return env


def parse_x509_cert_to_environ(cert, key_prefix):
    """Parse a cryptography x509 certificate into environ dict."""
    env = {}

    # Subject
    with suppress(Exception):
        subject = cert.subject
        components = [(attr.oid._name, attr.value) for attr in subject]
        env.update(_parse_dn_components(components, key_prefix, 'S'))

    # Issuer
    with suppress(Exception):
        issuer = cert.issuer
        components = [(attr.oid._name, attr.value) for attr in issuer]
        env.update(_parse_dn_components(components, key_prefix, 'I'))

    # Version and Serial
    with suppress(Exception):
        env[f'{key_prefix}_M_VERSION'] = str(cert.version.value)
        env[f'{key_prefix}_M_SERIAL'] = str(cert.serial_number)

    return env


class SSLEnvironMixin:
    """
    Mixin class providing methods for generating WSGI environment variables.

    This mixin handles GENERIC SSL environment variable generation that works
    across all SSL implementations. Adapter-specific logic (like certificate
    parsing) is delegated to subclass implementations.
    """

    def _get_core_tls_environ(self, conn):
        """
        Add core TLS version and cipher info to the environment.

        This is generic and works for all SSL adapters since TLSSocket
        provides a uniform get_cipher_info() interface.
        """
        cipher_info = conn.get_cipher_info()

        # Early exit if no cipher info (not a secure connection)
        if cipher_info is None:
            return {'wsgi.url_scheme': 'http'}

        cipher_name, protocol, cipher_keysize = cipher_info

        return {
            'wsgi.url_scheme': 'https',
            'HTTPS': 'on',
            'SSL_PROTOCOL': protocol,
            'SSL_CIPHER': cipher_name,
            'SSL_CIPHER_EXPORT': '',
            'SSL_CIPHER_USEKEYSIZE': cipher_keysize,
            'SSL_CLIENT_VERIFY': 'NONE',
        }

    def _get_server_cert_environ(self):
        """
        Get server certificate info from the connection.

        MUST be overridden by subclasses to provide adapter-specific parsing.
        Returns dict of SSL_SERVER_* environ variables.

        Default implementation returns empty dict.
        """
        return {}

    def _get_client_cert_environ(self, conn, ssl_environ):
        """
        Add client certificate details to the environment.

        SHOULD be overridden by subclasses for adapter-specific handling.
        Default implementation does nothing.
        """
        return ssl_environ


class Adapter(SSLEnvironMixin, ABC):
    """Base class for SSL driver library adapters.

    Required methods:

        * ``wrap(sock) -> (wrapped socket, ssl environ dict)``
        * ``_get_library_version_environ() -> dict``
        * ``_get_optional_environ(conn) -> dict``
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
        raise NotImplementedError

    def get_environ(self, conn):
        """
        Return WSGI environ entries to be merged into each request.

        Unified implementation used by all subclasses. This orchestrates
        the collection of SSL environment variables from various sources:
        - Core TLS info (protocol, cipher)
        - Library versions
        - Optional fields (SNI, etc.)
        - Session info
        - Client certificate
        - Server certificate

        Note: This returns only SSL-specific variables. General server
        variables (``SERVER_NAME``, ``SERVER_PORT``, etc.) are added by
        the Gateway when building the complete WSGI environ for each request.
        """
        # 1. Handle basic TLS info
        ssl_environ = self._get_core_tls_environ(conn)
        if 'HTTPS' not in ssl_environ:
            # Core TLS failed (returned 'http' env)
            return ssl_environ

        # 2. Update with library-specific version strings
        ssl_environ.update(self._get_library_version_environ())

        # 3. Handle optional/platform-specific fields (SNI, compression)
        ssl_environ.update(self._get_optional_environ(conn))

        # 4. Handle Session ID
        with suppress(AttributeError):
            session = conn.get_session()
            if session and hasattr(session, 'id'):
                ssl_environ['SSL_SESSION_ID'] = session.id.hex()

        # 5. Handle Client certificate (adapter-specific)
        ssl_environ = self._get_client_cert_environ(conn, ssl_environ)

        # 6. Server certificate (adapter-specific)
        server_cert_info = self._get_server_cert_environ()
        if server_cert_info:
            ssl_environ.update(server_cert_info)

        return ssl_environ

    @abstractmethod
    def _get_library_version_environ(self):
        """
        Get SSL library version information.

        Must be implemented by subclasses to provide adapter-specific
        version strings.

        Returns:
            dict: SSL_VERSION_INTERFACE and SSL_VERSION_LIBRARY
        """
        raise NotImplementedError

    @abstractmethod
    def _get_optional_environ(self, conn):
        """
        Get optional environment variables.

        Must be implemented by subclasses for adapter-specific handling
        of optional fields like SNI, compression, etc.

        Returns:
            dict: Optional SSL environment variables
        """
        raise NotImplementedError
