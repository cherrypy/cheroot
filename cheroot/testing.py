"""Pytest fixtures and other helpers for doing testing by end-users."""

import threading
import time

import pytest

import cheroot.server
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
