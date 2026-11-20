"""Check request-line terminators over real connections."""

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
    ('version', 'expected_status'),
    (
        (b'1.1 ', HTTPStatus.BAD_REQUEST),
        (b'1.1\t', HTTPStatus.BAD_REQUEST),
        (b'1.1\v', HTTPStatus.BAD_REQUEST),
        (b'1.1\f', HTTPStatus.BAD_REQUEST),
        (b'1.1\r', HTTPStatus.BAD_REQUEST),
        (b'1.1 \t', HTTPStatus.BAD_REQUEST),
        (b'1.0 ', HTTPStatus.BAD_REQUEST),
        (b'1.2 ', HTTPStatus.BAD_REQUEST),
        (b'1.0', HTTPStatus.OK),
        (b'1.1', HTTPStatus.OK),
        (b'1.2', HTTPStatus.HTTP_VERSION_NOT_SUPPORTED),
    ),
)
def test_request_line_trailing_whitespace(
    native_server: HTTPServer,
    http_request_timeout: float,
    version: bytes,
    expected_status: HTTPStatus,
) -> None:
    """Require the HTTP version to be followed immediately by CRLF.

    :param native_server: live HTTP server
    :param http_request_timeout: socket timeout in seconds
    :param version: version text including any extra whitespace
    :param expected_status: response required by the request-line grammar
    """
    native_server.gateway = _AcceptedGateway
    host, port = native_server.bind_addr
    request = b''.join(
        (
            b'GET / HTTP/',
            version,
            b'\r\nHost: localhost\r\nConnection: close\r\n\r\n',
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
