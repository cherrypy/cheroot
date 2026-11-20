"""Check forbidden characters in HTTP field values."""

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
    ('header_lines', 'expected_status'),
    (
        (b'Test: a\x00b', HTTPStatus.BAD_REQUEST),
        (b'Test: \x00', HTTPStatus.BAD_REQUEST),
        (b'Test: a\rb', HTTPStatus.BAD_REQUEST),
        (b'Test: \ra', HTTPStatus.BAD_REQUEST),
        (b'Test: a\r', HTTPStatus.BAD_REQUEST),
        (b'Test: \r a\r ', HTTPStatus.BAD_REQUEST),
        (b'Test: a\r\n b\x00c', HTTPStatus.BAD_REQUEST),
        (b'Test: a\r\n b\rc', HTTPStatus.BAD_REQUEST),
        (b'Test: a\nb', HTTPStatus.BAD_REQUEST),
        (b'Test: a\tb\x80', HTTPStatus.OK),
        (b'Test: a', HTTPStatus.OK),
        (b'Test: a\r\n b', HTTPStatus.OK),
    ),
)
def test_header_value_control_characters(
    native_server: HTTPServer,
    http_request_timeout: float,
    header_lines: bytes,
    expected_status: HTTPStatus,
) -> None:
    """Reject CR, LF and NUL in field values before trimming whitespace.

    :param native_server: live HTTP server
    :param http_request_timeout: socket timeout in seconds
    :param header_lines: field lines to send on the wire
    :param expected_status: response required by the field-value grammar
    """
    native_server.gateway = _AcceptedGateway
    host, port = native_server.bind_addr
    request = b''.join(
        (
            b'GET / HTTP/1.1\r\nHost: localhost\r\n',
            header_lines,
            b'\r\nConnection: close\r\n\r\n',
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
