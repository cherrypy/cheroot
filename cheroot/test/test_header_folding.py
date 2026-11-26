"""Preserve HTTP header values across continuation lines."""

from __future__ import annotations

import socket
from http import HTTPStatus
from http.client import HTTPResponse

import pytest

from cheroot.server import Gateway, HTTPServer
from cheroot.test import webtest


_CUSTOM_HEADER = b'X-Test'


class _HeaderGateway(Gateway):
    """Echo the header selected by the request path."""

    def respond(self) -> None:
        """Return the complete header value received by the application."""
        header_value = self.req.inheaders[self.req.path[1:]]
        self.req.status = b'200 OK'
        self.req.outheaders = [
            (b'Content-Length', str(len(header_value)).encode('ascii')),
        ]
        self.req.ensure_headers_sent()
        self.req.write(header_value)


@pytest.mark.parametrize(
    ('header_name', 'header_lines', 'expected_value'),
    (
        (_CUSTOM_HEADER, b'X-Test: a\r\n b\r\n\tc', b'a b c'),
        (b'Accept', b'Accept: a\r\n b\r\n\tc', b'a b c'),
        (_CUSTOM_HEADER, b'X-Test: a\r\n\t  b', b'a b'),
        (
            b'Accept',
            b'Accept: a\r\n b\r\nAccept: c\r\n d',
            b'a b, c d',
        ),
        (_CUSTOM_HEADER, b'X-Test: a\r\n b\r\nX-Test: c\r\n d', b'c d'),
        (_CUSTOM_HEADER, b'X-Test:\r\n b', b'b'),
        (b'Accept', b'Accept: a\r\nAccept: b', b'a, b'),
        (_CUSTOM_HEADER, b'X-Test: a', b'a'),
    ),
)
def test_header_continuation_values(
    native_server: HTTPServer,
    http_request_timeout: float,
    header_name: bytes,
    header_lines: bytes,
    expected_value: bytes,
) -> None:
    """Preserve continuation values and repeated header fields.

    :param native_server: live HTTP server
    :param http_request_timeout: socket timeout in seconds
    :param header_name: field to echo through the application
    :param header_lines: header bytes including any continuation lines
    :param expected_value: value required by the HTTP field rules
    """
    native_server.gateway = _HeaderGateway
    host, port = native_server.bind_addr
    request = b''.join(
        (
            b'GET /',
            header_name,
            b' HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n',
            header_lines,
            b'\r\n\r\n',
        ),
    )
    with socket.create_connection(
        (webtest.interface(host), port),
        timeout=http_request_timeout,
    ) as connection:
        connection.sendall(request)
        with HTTPResponse(connection) as response:
            response.begin()
            assert response.status == HTTPStatus.OK
            assert response.read() == expected_value
