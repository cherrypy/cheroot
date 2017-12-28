"""Pytest fixtures and other helpers for doing testing by end-users."""

from contextlib import closing
import errno
import socket
import threading
import time

import pytest
from six.moves import http_client

import cheroot.server
from cheroot.test import webtest
import cheroot.wsgi

EPHEMERAL_PORT = 0
NO_INTERFACE = None  # Using this or '' will cause an exception
ANY_INTERFACE_IPV4 = '0.0.0.0'
ANY_INTERFACE_IPV6 = '::'

config = {
    'bind_addr': (NO_INTERFACE, EPHEMERAL_PORT),
    'wsgi_app': None,
}


def cheroot_server(server_factory):
    """Set up and tear down a Cheroot server instance."""
    conf = config.copy()
    bind_port = conf.pop('bind_addr')[-1]

    for interface in ANY_INTERFACE_IPV6, ANY_INTERFACE_IPV4:
        try:
            actual_bind_addr = (interface, bind_port)
            httpserver = server_factory(  # create it
                bind_addr=actual_bind_addr,
                **conf
            )
        except OSError:
            pass
        else:
            break

    threading.Thread(target=httpserver.safe_start).start()  # spawn it
    while not httpserver.ready:  # wait until fully initialized and bound
        time.sleep(0.1)

    yield httpserver

    httpserver.stop()  # destroy it


@pytest.fixture(scope='module')
def wsgi_server():
    """Set up and tear down a Cheroot WSGI server instance."""
    for srv in cheroot_server(cheroot.wsgi.Server):
        yield srv


@pytest.fixture(scope='module')
def native_server():
    """Set up and tear down a Cheroot HTTP server instance."""
    for srv in cheroot_server(cheroot.server.HTTPServer):
        yield srv


@pytest.fixture(scope='module')
def server_client(wsgi_server):
    """Create a test client out of given server."""
    host, port = wsgi_server.bind_addr

    interface = webtest.interface(host)

    def probe_ipv6_sock(interface):
        # Alternate way is to check IPs on interfaces using glibc, like:
        # github.com/Gautier/minifail/blob/master/minifail/getifaddrs.py
        try:
            with closing(socket.socket(family=socket.AF_INET6)) as sock:
                sock.bind((interface, 0))
        except (OSError, socket.error) as sock_err:
            # In Python 3 socket.error is an alias for OSError
            # In Python 2 socket.error is a subclass of IOError
            if sock_err.errno != errno.EADDRNOTAVAIL:
                raise
        else:
            return True

        return False

    if ':' in interface and not probe_ipv6_sock(interface):
        interface = '127.0.0.1'
        if ':' in host:
            host = interface

    class _TestClient(object):
        def __init__(self, server, host, port):
            self._host = host
            self._port = port
            self._http_connection = self.get_connection()
            self.server_instance = server

        def get_connection(self):
            name = '{interface}:{port}'.format(
                interface=interface,
                port=self._port,
            )
            return http_client.HTTPConnection(name)

        def request(
            self, uri, method='GET', headers=None, http_conn=None,
            protocol='HTTP/1.1',
        ):
            return webtest.openURL(
                uri, method=method,
                headers=headers,
                host=self._host, port=self._port,
                http_conn=http_conn or self._http_connection,
                protocol=protocol,
            )

        def get(self, uri, **kwargs):
            return self.request(uri, method='GET', **kwargs)

        def head(self, uri, **kwargs):
            return self.request(uri, method='HEAD', **kwargs)

        def post(self, uri, **kwargs):
            return self.request(uri, method='POST', **kwargs)

        def put(self, uri, **kwargs):
            return self.request(uri, method='PUT', **kwargs)

        def patch(self, uri, **kwargs):
            return self.request(uri, method='PATCH', **kwargs)

        def delete(self, uri, **kwargs):
            return self.request(uri, method='DELETE', **kwargs)

        def connect(self, uri, **kwargs):
            return self.request(uri, method='CONNECT', **kwargs)

        def options(self, uri, **kwargs):
            return self.request(uri, method='OPTIONS', **kwargs)

    test_client = _TestClient(wsgi_server, host, port)
    return test_client
