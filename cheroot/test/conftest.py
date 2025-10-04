"""Pytest configuration module.

Contains fixtures, which are tightly bound to the Cheroot framework
itself, useless for end-users' app testing.
"""

import sys
import threading
import time

import pytest

from .._compat import IS_MACOS, IS_WINDOWS  # noqa: WPS436
from ..server import Gateway, HTTPServer
from ..testing import (  # noqa: F401  # pylint: disable=unused-import
    get_server_client,
    native_server,
    thread_and_native_server,
    thread_and_wsgi_server,
    wsgi_server,
)


# Python 3.14 compatibility: Force 'fork' multiprocessing start method
# Python 3.14 changed the default from 'fork' to 'forkserver' on Unix,
# which can cause issues with pytest-xdist's parallel test execution.
# This ensures compatibility with existing test fixtures and shared state.
# Ref: https://github.com/cherrypy/cheroot/issues/767
if sys.version_info >= (3, 14):
    try:
        import multiprocessing

        # Force fork method even if already set to forkserver
        multiprocessing.set_start_method('fork', force=True)
    except (ImportError, RuntimeError):
        # multiprocessing not available or already set and force failed
        pass


@pytest.fixture
def http_request_timeout():
    """Return a common HTTP request timeout for tests with queries."""
    computed_timeout = 0.1

    if IS_MACOS:
        computed_timeout *= 2

    if IS_WINDOWS:
        computed_timeout *= 10

    return computed_timeout


@pytest.fixture
# pylint: disable=redefined-outer-name
def wsgi_server_thread(thread_and_wsgi_server):  # noqa: F811
    """Set up and tear down a Cheroot WSGI server instance.

    This exposes the server thread.
    """
    server_thread, _srv = thread_and_wsgi_server
    return server_thread


@pytest.fixture
# pylint: disable=redefined-outer-name
def native_server_thread(thread_and_native_server):  # noqa: F811
    """Set up and tear down a Cheroot HTTP server instance.

    This exposes the server thread.
    """
    server_thread, _srv = thread_and_native_server
    return server_thread


@pytest.fixture
# pylint: disable=redefined-outer-name
def wsgi_server_client(wsgi_server):  # noqa: F811
    """Create a test client out of given WSGI server."""
    return get_server_client(wsgi_server)


@pytest.fixture
# pylint: disable=redefined-outer-name
def native_server_client(native_server):  # noqa: F811
    """Create a test client out of given HTTP server."""
    return get_server_client(native_server)


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
    next(srv_creator)  # pylint: disable=stop-iteration-return
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
