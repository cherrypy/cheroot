"""Reject ambiguous HTTP request body lengths."""

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
        (b'Content-Length: 0\r\nContent-Length: 1', HTTPStatus.BAD_REQUEST),
        (b'Content-Length: 1\r\nContent-Length: 0', HTTPStatus.BAD_REQUEST),
        (b'Content-Length: 1\r\nContent-Length: 1', HTTPStatus.BAD_REQUEST),
        (b'Content-Length: 0\r\ncontent-length: 1', HTTPStatus.BAD_REQUEST),
        (b'content-length: 0\r\nCONTENT-LENGTH: 1', HTTPStatus.BAD_REQUEST),
        (b'Content-Length: 1\r\nConnection: close', HTTPStatus.OK),
    ),
)
def test_duplicate_content_length(
    native_server: HTTPServer,
    http_request_timeout: float,
    header_lines: bytes,
    expected_status: HTTPStatus,
) -> None:
    """Reject duplicate lengths and close before any following request.

    :param native_server: live HTTP server
    :param http_request_timeout: socket timeout in seconds
    :param header_lines: length fields to send on the wire
    :param expected_status: response required by the framing rules
    """
    native_server.gateway = _AcceptedGateway
    host, port = native_server.bind_addr
    request = b''.join(
        (
            b'POST / HTTP/1.1\r\nHost: localhost\r\n',
            header_lines,
            b'\r\n\r\naGET / HTTP/1.1\r\nHost: localhost\r\n\r\n',
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
