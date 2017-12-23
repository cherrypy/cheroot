import threading
import time

import pytest

import cheroot.server
import cheroot.wsgi

EPHEMERAL_PORT = 0

config = {
    'bind_addr': ('127.0.0.1', EPHEMERAL_PORT),
    'wsgi_app': None,
}


def cheroot_server(server_factory):
    conf = config.copy()
    httpserver = server_factory(**conf)  # create it

    threading.Thread(target=httpserver.safe_start).start()  # spawn it
    while not httpserver.ready:  # wait until fully initialized and bound
        time.sleep(0.1)

    yield httpserver

    httpserver.stop()  # destroy it


@pytest.fixture(scope='module')
def wsgi_server():
    for srv in cheroot_server(cheroot.wsgi.Server):
        yield srv


@pytest.fixture(scope='module')
def native_server():
    for srv in cheroot_server(cheroot.server.HTTPServer):
        yield srv
