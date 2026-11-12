"""Test wsgi."""

import socket
from concurrent.futures.thread import ThreadPoolExecutor
from functools import partial
from traceback import print_tb

import pytest

import portend
import requests
from jaraco.context import ExceptionTrap
from requests_toolbelt.sessions import BaseUrlSession as Session

from cheroot import wsgi
from cheroot._compat import IS_MACOS, IS_WINDOWS


IS_SLOW_ENV = IS_MACOS or IS_WINDOWS


@pytest.fixture
def simple_wsgi_server():
    """Fucking simple wsgi server fixture (duh)."""
    port = portend.find_available_local_port()

    def app(_environ, start_response):
        status = '200 OK'
        response_headers = [('Content-type', 'text/plain')]
        start_response(status, response_headers)
        return [b'Hello world!']

    host = '::'
    addr = host, port
    server = wsgi.Server(addr, app, timeout=600 if IS_SLOW_ENV else 20)
    # pylint: disable=possibly-unused-variable
    url = 'http://localhost:{port}/'.format(**locals())
    # pylint: disable=possibly-unused-variable
    with server._run_in_thread() as thread:
        yield locals()


@pytest.mark.flaky(reruns=3, reruns_delay=2)
def test_connection_keepalive(simple_wsgi_server):
    """Test the connection keep-alive works (duh)."""
    session = Session(base_url=simple_wsgi_server['url'])
    pooled = requests.adapters.HTTPAdapter(
        pool_connections=1,
        pool_maxsize=1000,
    )
    session.mount('http://', pooled)

    def do_request():
        with ExceptionTrap(requests.exceptions.ConnectionError) as trap:
            resp = session.get('info')
            resp.raise_for_status()
        print_tb(trap.tb)
        return bool(trap)

    with ThreadPoolExecutor(max_workers=10 if IS_SLOW_ENV else 50) as pool:
        tasks = [
            pool.submit(do_request)
            for n in range(250 if IS_SLOW_ENV else 1000)
        ]
        failures = sum(task.result() for task in tasks)

    session.close()
    assert not failures


def test_gateway_start_response_called_twice(monkeypatch):
    """Verify that repeat calls of ``Gateway.start_response()`` fail."""
    monkeypatch.setattr(wsgi.Gateway, 'get_environ', lambda self: {})
    wsgi_gateway = wsgi.Gateway(None)
    wsgi_gateway.started_response = True

    err_msg = '^WSGI start_response called a second time with no exc_info.$'
    with pytest.raises(RuntimeError, match=err_msg):
        wsgi_gateway.start_response('200', (), None)


def test_gateway_write_needs_start_response_called_before(monkeypatch):
    """Check that calling ``Gateway.write()`` needs started response."""
    monkeypatch.setattr(wsgi.Gateway, 'get_environ', lambda self: {})
    wsgi_gateway = wsgi.Gateway(None)

    err_msg = '^WSGI write called before start_response.$'
    with pytest.raises(RuntimeError, match=err_msg):
        wsgi_gateway.write(None)  # The actual arg value is unimportant


@pytest.mark.parametrize(
    ('length', 'chunks', 'expected', 'errors'),
    (
        ('5', (b'abc', b'def'), b'abcde', 1),
        ('4', (b'abcd', b'e'), b'abcd', 1),
        ('3', (b'ab', b'cdef', b'ghij'), b'abc', 2),
        ('6', (b'abcd', b'ef'), b'abcdef', 0),
        (None, (b'abcde', b'f'), b'abcdef', 0),
    ),
)
def test_gateway_response_length(
    mocker,
    length,
    chunks,
    expected,
    errors,
):
    """Writes share one length budget, even after a caught overflow."""
    mocker.patch.object(wsgi.Gateway, 'get_environ', return_value={})
    req = mocker.Mock(sent_headers=False, outheaders=[])
    gateway = wsgi.Gateway(req)
    headers = [] if length is None else [('Content-Length', length)]
    write = gateway.start_response('200 OK', headers)
    caught = 0
    for chunk in chunks:
        try:
            write(chunk)
        except ValueError:
            caught += 1
        req.sent_headers = True
    assert caught == errors
    assert (
        b''.join(call.args[0] for call in req.write.call_args_list) == expected
    )
    assert gateway.remaining_bytes_out == (None if length is None else 0)


@pytest.mark.parametrize('use_write', (False, True))
def test_wsgi_truncates_response_length(wsgi_server, use_write):
    """A streaming app cannot send bytes past its declared body length."""

    def app(_environ, start_response):
        write = start_response('200 OK', [('Content-Length', '5')])
        chunks = (b'abc', b'def')
        if use_write:
            for chunk in chunks:
                write(chunk)
            return []
        return chunks

    wsgi_server.wsgi_app = app
    with socket.create_connection(
        ('localhost', wsgi_server.bind_addr[1]),
    ) as conn:
        conn.settimeout(10)
        conn.sendall(
            b'GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n',
        )
        response = bytearray()
        for chunk in iter(partial(conn.recv, 4096), b''):
            response.extend(chunk)
    headers, _, body = bytes(response).partition(b'\r\n\r\n')
    assert headers.startswith(b'HTTP/1.1 200 OK')
    assert body == b'abcde'
