"""Test SSL port contention issues."""

import os
import socket
import tempfile
import threading
import time
import unittest

import pytest

import trustme

from .. import server
from ..ssl import builtin


class SSLPortContentionTest(unittest.TestCase):
    """Test SSL port contention scenarios."""

    @pytest.mark.skipif(not builtin.ssl, reason='builtin SSL support required')
    def test_builtin_ssl_with_incomplete_handshake(self):
        """Test that builtin SSL adapter handles incomplete handshakes."""
        # Create temporary certificate
        ca = trustme.CA()
        cert = ca.issue_cert('localhost')

        with tempfile.NamedTemporaryFile(delete=False) as cert_file:
            cert_file.write(cert.cert_chain_pems[0].bytes())
            cert_path = cert_file.name

        with tempfile.NamedTemporaryFile(delete=False) as key_file:
            key_file.write(cert.private_key_pem.bytes())
            key_path = key_file.name

        try:
            # Create a simple server
            srv = server.HTTPServer(
                bind_addr=('127.0.0.1', 0),
                gateway=None,
            )
            srv.ssl_adapter = builtin.BuiltinSSLAdapter(
                certificate=cert_path,
                private_key=key_path,
            )

            # Start server in a thread
            server_thread = threading.Thread(target=srv.safe_start)
            server_thread.daemon = True
            server_thread.start()

            # Wait for server to start
            time.sleep(0.1)

            # Create a raw TCP connection without completing handshake
            sock = socket.create_connection(srv.bind_addr)

            # Verify we can still connect with a proper SSL client
            try:
                import ssl

                ssl_sock = ssl.wrap_socket(
                    socket.create_connection(srv.bind_addr),
                    ssl_version=ssl.PROTOCOL_TLS,
                )
                ssl_sock.close()
                success = True
            except Exception:
                success = False

            # Clean up
            sock.close()
            srv.stop()
            server_thread.join()

            self.assertTrue(
                success,
                'Should be able to connect with SSL client',
            )
        finally:
            os.unlink(cert_path)
            os.unlink(key_path)
