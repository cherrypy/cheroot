"""Pytest fixtures and other helpers for doing testing by end-users."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import errno
import socket
import threading
import time
import logging
import traceback as traceback_
from contextlib import closing
from collections import namedtuple

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
    cheroot.wsgi.Server: {
        'bind_addr': (NO_INTERFACE, EPHEMERAL_PORT),
        'wsgi_app': None,
    },
    cheroot.server.HTTPServer: {
        'bind_addr': (NO_INTERFACE, EPHEMERAL_PORT),
        'gateway': cheroot.server.Gateway,
    },
}


def cheroot_server(server_factory):
    """Set up and tear down a Cheroot server instance."""
    conf = config[server_factory].copy()
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

    httpserver.shutdown_timeout = 0  # Speed-up tests teardown

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


class _TestClient:
    def __init__(self, server):
        self._interface, self._host, self._port = _get_conn_data(
            server.bind_addr,
        )
        self.server_instance = server
        self._http_connection = self.get_connection()

    def get_connection(self):
        name = '{interface}:{port}'.format(
            interface=self._interface,
            port=self._port,
        )
        conn_cls = (
            http_client.HTTPConnection
            if self.server_instance.ssl_adapter is None else
            http_client.HTTPSConnection
        )
        return conn_cls(name)

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

    def __getattr__(self, attr_name):
        def _wrapper(uri, **kwargs):
            http_method = attr_name.upper()
            return self.request(uri, method=http_method, **kwargs)

        return _wrapper


def _probe_ipv6_sock(interface):
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


def _get_conn_data(bind_addr):
    if isinstance(bind_addr, tuple):
        host, port = bind_addr
    else:
        host, port = bind_addr, 0

    interface = webtest.interface(host)

    if ':' in interface and not _probe_ipv6_sock(interface):
        interface = '127.0.0.1'
        if ':' in host:
            host = interface

    return interface, host, port


def get_server_client(server):
    """Create and return a test client for the given server."""
    return _TestClient(server)


class ErrorLogMonitor:
    """Mock class to access the server error_log calls made by the server."""

    ErrorLogCall = namedtuple('ErrorLogCall', ['msg', 'level', 'traceback'])

    def __init__(self):
        """Initialize the server error log monitor/interceptor.

        If you need to ignore a particular error message use the property
        ``ignored_msgs` by appending to the list the expected error messages.
        """
        self.calls = []
        # to be used the the teardown validation
        self.ignored_msgs = []

    def __call__(self, msg='', level=logging.INFO, traceback=False):
        """Intercept the call to the server error_log method."""
        if traceback:
            tblines = traceback_.format_exc()
        else:
            tblines = ''
        self.calls.append(ErrorLogMonitor.ErrorLogCall(msg, level, tblines))

    def _teardown_verification(self):
        # Teardown verification, in case that the server logged an
        # error that wasn't notified to the client or we just made a mistake.
        for c_msg, c_level, c_traceback in self.calls:
            if c_level < logging.WARNING:
                continue
            if c_msg in self.ignored_msgs:
                continue
            # raise the explicit AssertionError, instead of the
            # assert statement, it provides a default behavior
            # that will show the full traceback to debug.
            raise AssertionError(
                'Found error in the error log: '
                "message = '{c_msg}', level = '{c_level}'\n"
                '{c_traceback}'.format(**locals()),
            )
