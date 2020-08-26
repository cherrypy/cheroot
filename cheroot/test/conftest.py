"""Pytest configuration module.

Contains fixtures, which are tightly bound to the Cheroot framework
itself, useless for end-users' app testing.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import threading
import time

import pytest

from ..server import Gateway, HTTPServer
from ..testing import (  # noqa: F401
    native_server, wsgi_server,
)
from ..testing import get_server_client, ErrorLogMonitor


@pytest.fixture
def wsgi_server_client(wsgi_server, monkeypatch):  # noqa: F811
    """Create a test client out of given WSGI server.

    If you need to ignore a particular error message use the property
    ``error_log.ignored_msgs`` by appending to the list
    the expected error messages.
    """
    monkeypatch.setattr(wsgi_server, 'error_log', ErrorLogMonitor())
    yield get_server_client(wsgi_server)
    wsgi_server.error_log._teardown_verification()


@pytest.fixture
def native_server_client(native_server, monkeypatch):  # noqa: F811
    """Create a test client out of given HTTP server.

    If you need to ignore a particular error message use the property
    ``error_log.ignored_msgs`` by appending to the list
    the expected error messages.
    """
    monkeypatch.setattr(native_server, 'error_log', ErrorLogMonitor())
    yield get_server_client(native_server)
    native_server.error_log._teardown_verification()


@pytest.fixture
def http_server():
    """Provision a server creator as a fixture."""
    def start_srv():
        bind_addr = yield
        if bind_addr is None:
            return
        httpserver = make_http_server(bind_addr)
        yield httpserver
        yield httpserver

    srv_creator = iter(start_srv())
    next(srv_creator)
    yield srv_creator
    try:
        while True:
            httpserver = next(srv_creator)
            if httpserver is not None:
                httpserver.stop()
    except StopIteration:
        pass


def make_http_server(bind_addr):
    """Create and start an HTTP server bound to ``bind_addr``."""
    httpserver = HTTPServer(
        bind_addr=bind_addr,
        gateway=Gateway,
    )

    threading.Thread(target=httpserver.safe_start).start()

    while not httpserver.ready:
        time.sleep(0.1)

    return httpserver
