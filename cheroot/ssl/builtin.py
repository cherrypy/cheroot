"""
A library for integrating Python's builtin :py:mod:`ssl` library with Cheroot.

The :py:mod:`ssl` module must be importable for SSL functionality.

To use this module, set ``HTTPServer.ssl_adapter`` to an instance of
``BuiltinSSLAdapter``.
"""

import socket
import sys
from contextlib import suppress

from . import Adapter
from .tls_socket import TLSSocket


try:
    import ssl
except ImportError:
    ssl = None

try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
except ImportError:
    x509 = None
    default_backend = None


from .. import errors
from . import parse_x509_cert_to_environ


class BuiltinSSLAdapter(Adapter):
    """
    Wrapper for integrating Python's builtin :py:mod:`ssl` with Cheroot.

    This adapter uses TLSSocket internally to provide a consistent
    interface for SSL/TLS connections.
    """

    certificate = None
    """The file name of the server SSL certificate."""

    private_key = None
    """The file name of the server's private key file."""

    certificate_chain = None
    """The file name of the certificate chain file."""

    ciphers = None
    """The ciphers list of SSL."""

    private_key_password = None
    """Optional passphrase for password protected private key."""

    # from mod_ssl/pkg.sslmod/ssl_engine_vars.c ssl_var_lookup_ssl_cert
    CERT_KEY_TO_ENV = {
        'version': 'M_VERSION',
        'serialNumber': 'M_SERIAL',
        'notBefore': 'V_START',
        'notAfter': 'V_END',
        'subject': 'S_DN',
        'issuer': 'I_DN',
        'subjectAltName': 'SAN',
        # not parsed by the Python standard library
        # - A_SIG
        # - A_KEY
        # not provided by mod_ssl
        # - OCSP
        # - caIssuers
        # - crlDistributionPoints
    }

    # from mod_ssl/pkg.sslmod/ssl_engine_vars.c ssl_var_lookup_ssl_cert_dn_rec
    CERT_KEY_TO_LDAP_CODE = {
        'countryName': 'C',
        'stateOrProvinceName': 'ST',
        # NOTE: mod_ssl also provides 'stateOrProvinceName' as 'SP'
        # for compatibility with SSLeay
        'localityName': 'L',
        'organizationName': 'O',
        'organizationalUnitName': 'OU',
        'commonName': 'CN',
        'title': 'T',
        'initials': 'I',
        'givenName': 'G',
        'surname': 'S',
        'description': 'D',
        'userid': 'UID',
        'emailAddress': 'Email',
        # not provided by mod_ssl
        # - dnQualifier: DNQ
        # - domainComponent: DC
        # - postalCode: PC
        # - streetAddress: STREET
        # - serialNumber
        # - generationQualifier
        # - pseudonym
        # - jurisdictionCountryName
        # - jurisdictionLocalityName
        # - jurisdictionStateOrProvince
        # - businessCategory
    }

    def __init__(
        self,
        certificate,
        private_key,
        certificate_chain=None,
        ciphers=None,
        *,
        private_key_password=None,
    ):
        """Initialize builtin SSL Adapter instance."""
        if ssl is None:
            raise ImportError(
                'You must have ssl module available to use HTTPS.',
            )

        super().__init__(
            certificate,
            private_key,
            certificate_chain,
            ciphers,
            private_key_password=private_key_password,
        )

        self._context = None
        self._context = self._create_context()

    def bind(self, sock):
        """Prepare the server socket."""
        return sock  # Context already created

    def wrap(self, sock):
        """
        Wrap client socket with SSL and return environ entries.

        Args:
            sock: Raw socket to wrap with TLS

        Returns:
            tuple: (TLSSocket, ssl_environ_dict)
        """
        if self._check_for_plain_http(sock):
            raise errors.NoSSLError

        tls_socket = self._wrap_with_builtin(sock)
        ssl_environ = self.get_environ(tls_socket)
        return tls_socket, ssl_environ

    def _wrap_with_builtin(self, raw_socket, server_side=True):
        """
        Create a TLSSocket using Python's built-in ssl module.

        Args:
            raw_socket: The raw socket to wrap
            server_side: True if this is the server side

        Returns:
            TLSSocket: Wrapped socket ready for secure I/O
        """
        try:
            wrapped_ssl_socket = self._create_ssl_socket(
                raw_socket,
                server_side,
            )
            self._perform_handshake(wrapped_ssl_socket, raw_socket)

            underlying_socket = wrapped_ssl_socket
            if hasattr(wrapped_ssl_socket, '_sock'):
                underlying_socket = wrapped_ssl_socket._sock

            return TLSSocket(
                ssl_socket=wrapped_ssl_socket,
                raw_socket=underlying_socket,
                context=self.context,
            )
        except errors.NoSSLError:
            # Plain HTTP detected, let it propagate for proper error response
            raise
        except TimeoutError:
            # Handshake timeout, let it propagate
            with suppress(Exception):
                raw_socket.close()
            raise
        except (ssl.SSLError, OSError) as e:
            # SSL handshake or socket error - clean up and raise
            with suppress(Exception):
                raw_socket.close()
            raise errors.FatalSSLAlert(f'SSL wrapping failed: {e}') from e

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
        try:
            raw_socket.settimeout(PEEK_TIMEOUT)
            first_bytes = raw_socket.recv(PEEK_BYTES, socket.MSG_PEEK)

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
            return any(
                first_bytes.startswith(method) for method in http_methods
            )
        except (OSError, socket.timeout):
            return False
        finally:
            raw_socket.settimeout(original_timeout)

    def _create_ssl_socket(self, raw_socket, server_side):
        """Create SSL socket without handshake."""
        try:
            # Manual handshake for error handling
            return self.context.wrap_socket(
                raw_socket,
                do_handshake_on_connect=False,
                server_side=server_side,
            )
        except ssl.SSLError as e:
            raise errors.FatalSSLAlert(
                f'Error creating SSL socket: {e}',
            ) from e

    def _perform_handshake(self, ssl_socket, raw_socket):
        """Perform SSL handshake with error handling and retries."""
        HANDSHAKE_TIMEOUT = 5.0

        # Set timeout on the SSL socket for the handshake
        original_timeout = ssl_socket.gettimeout()
        ssl_socket.settimeout(HANDSHAKE_TIMEOUT)

        try:
            while True:
                try:  # noqa: WPS225
                    ssl_socket.do_handshake()
                    return
                except (ssl.SSLWantReadError, ssl.SSLWantWriteError) as e:
                    direction = (
                        'read'
                        if isinstance(e, ssl.SSLWantReadError)
                        else 'write'
                    )
                    self._wait_for_handshake_data(raw_socket, direction)
                except socket.timeout as e:
                    raise errors.NoSSLError(
                        'SSL handshake timeout.',
                    ) from e
                except ssl.SSLEOFError as e:
                    raise errors.NoSSLError(
                        'Peer closed connection during handshake.',
                    ) from e
                except ssl.SSLError as e:
                    self._handle_ssl_error(e)
                except OSError as e:
                    raise errors.FatalSSLAlert(
                        f'TCP error during handshake: {e}',
                    ) from e
        finally:
            # Restore original timeout
            with suppress(Exception):
                ssl_socket.settimeout(original_timeout)

    def _wait_for_handshake_data(self, raw_socket, direction):
        """Wait for socket to be ready for read or write during handshake."""
        import select

        HANDSHAKE_TIMEOUT = 5.0
        fileno = raw_socket.fileno()

        if direction == 'read':
            ready = select.select([fileno], [], [], HANDSHAKE_TIMEOUT)[0]
        else:  # write
            ready = select.select([], [fileno], [], HANDSHAKE_TIMEOUT)[1]

        if not ready:
            raise TimeoutError(
                f'Handshake failed: Peer did not send expected data ({direction}).',
            )

    def _handle_ssl_error(self, error):
        """Handle SSL errors during handshake."""
        err_str = str(error).lower()

        # Check for common patterns indicating plain HTTP
        if any(
            pattern in err_str
            for pattern in (
                'wrong version number',
                'http request',
                'unknown protocol',
            )
        ):
            raise errors.NoSSLError(
                'Client sent plain HTTP request',
            ) from error

        raise errors.FatalSSLAlert(
            f'Fatal SSL error during handshake: {error}',
        ) from error

    @property
    def context(self):
        """Get the SSL context."""
        return self._context

    @context.setter
    def context(self, value):
        """Set the SSL context (for testing)."""
        self._context = value

    def _create_context(self):
        """Return an py:class:`ssl.SSLContext` from self attributes."""
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

        ctx.minimum_version = ssl.TLSVersion.TLSv1_2

        # Only attempt to load the key/cert chain if a certificate
        # path is available.
        if self.certificate:
            try:
                ctx.load_cert_chain(
                    self.certificate,
                    self.private_key,
                    self.private_key_password,
                )
            except FileNotFoundError as file_err:
                raise FileNotFoundError(
                    f'SSL certificate file not found: {file_err}',
                ) from file_err

        # Load CA Trust/Verification Chain
        # (Optional, independent of server cert)
        # This is needed for verifying client certificates
        # or connecting to other services.
        if self.certificate_chain:
            ctx.load_verify_locations(cafile=self.certificate_chain)

        # Set Ciphers (Optional, independent of server cert)
        if self.ciphers:
            ctx.set_ciphers(self.ciphers)

        return ctx

    # ========================================================================
    # Adapter-specific environment variable methods
    # ========================================================================

    def _get_library_version_environ(self):
        """
        Get SSL library version information.

        Overrides base class method to provide builtin ssl module version.
        """
        python_version = sys.version.split()[0]
        return {
            'SSL_VERSION_INTERFACE': f'Python/{python_version} {ssl.OPENSSL_VERSION}',
            'SSL_VERSION_LIBRARY': ssl.OPENSSL_VERSION,
        }

    def _get_optional_environ(self, conn):
        """
        Get optional environment variables.

        Overrides base class method for builtin ssl-specific handling.
        """
        environ = {}

        # Compression (note: most modern OpenSSL builds disable compression)
        try:
            compression = conn.compression()
            if compression:
                environ['SSL_COMPRESS_METHOD'] = compression
        except AttributeError:
            # TLSSocket might not have compression method
            ...

        # SNI (Server Name Indication) if available
        try:
            server_hostname = conn.server_hostname
            if server_hostname:
                environ['SSL_TLS_SNI'] = server_hostname
        except AttributeError:
            ...

        return environ

    def _get_server_cert_environ(self):
        """Get server certificate info using builtin ssl certificate parsing."""
        if not self.certificate:
            return {}

        # Check if cryptography is available
        if x509 is None:
            return {}

        try:
            with open(self.certificate, 'rb') as cert_file:
                cert_data = cert_file.read()

            cert = x509.load_pem_x509_certificate(
                cert_data,
                default_backend(),
            )

            return parse_x509_cert_to_environ(cert, 'SSL_SERVER')

        except Exception:
            return {}

    def _get_client_cert_environ(self, conn, ssl_environ):
        """Populate the WSGI environment with client certificate details."""
        # 1. Access the raw ssl.SSLSocket object
        try:
            # 'conn' is the TLSSocket wrapper; '_sock' is the raw ssl.SSLSocket
            raw_ssl_socket = conn._sock
        except AttributeError:
            # If the socket is missing or already closed
            ssl_environ['SSL_CLIENT_VERIFY'] = 'NONE'
            return ssl_environ

        # 2. Get the peer certificate details
        try:
            # getpeercert() returns a dict if a cert was presented,
            # None otherwise.
            peer_cert_details = raw_ssl_socket.getpeercert(binary_form=False)
            # Also get the binary (DER) form to convert to PEM
            peer_cert_binary = raw_ssl_socket.getpeercert(binary_form=True)
        except ssl.SSLError:
            # This occurs if verification failed during the handshake
            ssl_environ['SSL_CLIENT_VERIFY'] = 'FAILURE'
            return ssl_environ
        except Exception:
            # Catch any other socket errors
            ssl_environ['SSL_CLIENT_VERIFY'] = 'NONE'
            return ssl_environ

        # --- Check Verification Status ---
        if peer_cert_details:
            ssl_environ['SSL_CLIENT_VERIFY'] = 'SUCCESS'
        else:
            # No cert presented
            ssl_environ['SSL_CLIENT_VERIFY'] = 'NONE'
            return ssl_environ

        # --- Add the PEM-encoded certificate ---
        if peer_cert_binary:
            ssl_environ['SSL_CLIENT_CERT'] = ssl.DER_cert_to_PEM_cert(
                peer_cert_binary,
            )

        # --- Populate Metadata using existing utility methods ---

        # 3. Populate Subject DN
        subject_dn_nested = peer_cert_details.get('subject', [])
        subject_env = self._make_env_dn_dict(
            env_prefix='SSL_CLIENT_S_DN',
            cert_value=subject_dn_nested,
        )
        ssl_environ.update(subject_env)

        # 4. Populate Issuer DN
        issuer_dn_nested = peer_cert_details.get('issuer', [])
        issuer_env = self._make_env_dn_dict(
            env_prefix='SSL_CLIENT_I_DN',
            cert_value=issuer_dn_nested,
        )
        ssl_environ.update(issuer_env)

        # 5. Populate other cert details
        ssl_environ['SSL_CLIENT_M_VERSION'] = str(
            peer_cert_details.get('version', ''),
        )
        ssl_environ['SSL_CLIENT_M_SERIAL'] = str(
            peer_cert_details.get('serialNumber', ''),
        )

        return ssl_environ

    def _make_env_cert_dict(self, env_prefix, parsed_cert):
        """Return a dict of WSGI environment variables for a certificate.

        E.g. SSL_CLIENT_M_VERSION, SSL_CLIENT_M_SERIAL, etc.
        See https://httpd.apache.org/docs/2.4/mod/mod_ssl.html#envvars.
        """
        if not parsed_cert:
            return {}

        env = {}
        for cert_key, env_var in self.CERT_KEY_TO_ENV.items():
            key = '%s_%s' % (env_prefix, env_var)
            value = parsed_cert.get(cert_key)
            if env_var == 'SAN':
                env.update(self._make_env_san_dict(key, value))
            elif env_var.endswith('_DN'):
                env.update(self._make_env_dn_dict(key, value))
            else:
                env[key] = str(value)

        # mod_ssl 2.1+; Python 3.2+
        # number of days until the certificate expires
        if 'notBefore' in parsed_cert:
            remain = ssl.cert_time_to_seconds(parsed_cert['notAfter'])
            remain -= ssl.cert_time_to_seconds(parsed_cert['notBefore'])
            remain /= 60 * 60 * 24
            env['%s_V_REMAIN' % (env_prefix,)] = str(int(remain))

        return env

    def _make_env_san_dict(self, env_prefix, cert_value):
        """Return a dict of WSGI environment variables for a certificate DN.

        E.g. SSL_CLIENT_SAN_Email_0, SSL_CLIENT_SAN_DNS_0, etc.
        See SSL_CLIENT_SAN_* at
        https://httpd.apache.org/docs/2.4/mod/mod_ssl.html#envvars.
        """
        if not cert_value:
            return {}

        env = {}
        dns_count = 0
        email_count = 0
        for attr_name, val in cert_value:
            if attr_name == 'DNS':
                env['%s_DNS_%i' % (env_prefix, dns_count)] = val
                dns_count += 1
            elif attr_name == 'Email':
                env['%s_Email_%i' % (env_prefix, email_count)] = val
                email_count += 1

        # other mod_ssl SAN vars:
        # - SAN_OTHER_msUPN_n
        return env

    def _make_env_dn_dict(self, env_prefix, cert_value):
        """Return a dict of WSGI environment variables for a certificate DN.

        E.g. SSL_CLIENT_S_DN_CN, SSL_CLIENT_S_DN_C, etc.
        See SSL_CLIENT_S_DN_x509 at
        https://httpd.apache.org/docs/2.4/mod/mod_ssl.html#envvars.
        """
        if not cert_value:
            return {}

        dn = []
        dn_attrs = {}
        for rdn in cert_value:
            for attr_name, val in rdn:
                attr_code = self.CERT_KEY_TO_LDAP_CODE.get(attr_name)
                dn.append('%s=%s' % (attr_code or attr_name, val))
                if not attr_code:
                    continue
                dn_attrs.setdefault(attr_code, [])
                dn_attrs[attr_code].append(val)

        dn_string = '/'.join(dn)

        env = {
            env_prefix: '/%s' % (dn_string,),
        }
        for attr_code, values in dn_attrs.items():
            env['%s_%s' % (env_prefix, attr_code)] = ','.join(values)
            if len(values) == 1:
                continue
            for i, val in enumerate(values):
                env['%s_%s_%i' % (env_prefix, attr_code, i)] = val
        return env
