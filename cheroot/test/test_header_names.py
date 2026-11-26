"""Exercise HTTP header parsing over real connections."""

from __future__ import annotations

import socket
from http import HTTPStatus
from http.client import HTTPResponse

import pytest

from cheroot.server import Gateway, HTTPServer
from cheroot.test import webtest


class _AcceptedGateway(Gateway):
    """Acknowledge requests that reach the application."""

    def respond(self) -> None:
        """Send an empty successful response."""
        self.req.status = b'200 OK'
        self.req.outheaders = [(b'Content-Length', b'0')]


@pytest.mark.parametrize(
    ('header_name', 'expected_status'),
    (
        (b'', HTTPStatus.BAD_REQUEST),
        (b'Test ', HTTPStatus.BAD_REQUEST),
        (b'Test\t', HTTPStatus.BAD_REQUEST),
        (b'Test\v', HTTPStatus.BAD_REQUEST),
        (b'Test\f', HTTPStatus.BAD_REQUEST),
        (b'Test\r', HTTPStatus.BAD_REQUEST),
        (b'Content-Length ', HTTPStatus.BAD_REQUEST),
        (b'Te st', HTTPStatus.BAD_REQUEST),
        (b'Te(st)', HTTPStatus.BAD_REQUEST),
        (b'Te\x00st', HTTPStatus.BAD_REQUEST),
        (b'Test\x80', HTTPStatus.BAD_REQUEST),
        (b'Test', HTTPStatus.OK),
        (b'tEsT', HTTPStatus.OK),
        (b"!#$%&'*+-.^_`|~0123456789aZ", HTTPStatus.OK),
    ),
)
def test_header_name_grammar(
    native_server: HTTPServer,
    http_request_timeout: float,
    header_name: bytes,
    expected_status: HTTPStatus,
) -> None:
    """Accept only nonempty HTTP tokens as header names.

    :param native_server: live HTTP server
    :param http_request_timeout: socket timeout in seconds
    :param header_name: field name to send on the wire
    :param expected_status: response required by the HTTP token grammar
    """
    native_server.gateway = _AcceptedGateway
    host, port = native_server.bind_addr
    request = b''.join(
        (
            b'GET / HTTP/1.1\r\nHost: localhost\r\n',
            header_name,
            b': 0\r\nConnection: close\r\n\r\n',
        ),
    )
    with socket.create_connection(
        (webtest.interface(host), port),
        timeout=http_request_timeout,
    ) as connection:
        connection.sendall(request)
        with HTTPResponse(connection) as response:
            response.begin()
            assert response.status == expected_status
            response.read()
        assert connection.recv(1) == b''
