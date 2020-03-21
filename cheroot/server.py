"""
A high-speed, production ready, thread pooled, generic HTTP server.

For those of you wanting to understand internals of this module, here's the
basic call flow. The server's listening thread runs a very tight loop,
sticking incoming connections onto a Queue::

    server = HTTPServer(...)
    server.start()
    ->  while True:
            tick()
            # This blocks until a request comes in:
            child = socket.accept()
            conn = HTTPConnection(child, ...)
            server.requests.put(conn)

Worker threads are kept in a pool and poll the Queue, popping off and then
handling each connection in turn. Each connection can consist of an arbitrary
number of requests and their responses, so we run a nested loop::

    while True:
        conn = server.requests.get()
        conn.communicate()
        ->  while True:
                req = HTTPRequest(...)
                req.parse_request()
                ->  # Read the Request-Line, e.g. "GET /page HTTP/1.1"
                    req.rfile.readline()
                    read_headers(req.rfile, req.inheaders)
                req.respond()
                ->  response = app(...)
                    try:
                        for chunk in response:
                            if chunk:
                                req.write(chunk)
                    finally:
                        if hasattr(response, "close"):
                            response.close()
                if req.close_connection:
                    return

For running a server you can invoke :func:`start() <HTTPServer.start()>` (it
will run the server forever) or use invoking :func:`prepare()
<HTTPServer.prepare()>` and :func:`serve() <HTTPServer.serve()>` like this::

    server = HTTPServer(...)
    server.prepare()
    try:
        threading.Thread(target=server.serve).start()

        # waiting/detecting some appropriate stop condition here
        ...

    finally:
        server.stop()

And now for a trivial doctest to exercise the test suite

>>> 'HTTPServer' in globals()
True
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import os
import io
import re
import email.utils
import socket
import sys
import time
import traceback as traceback_
import logging
import platform
from abc import ABC, abstractmethod

try:
    from functools import lru_cache
except ImportError:
    from backports.functools_lru_cache import lru_cache

import h11
import six
from six.moves import queue
from six.moves import urllib

from . import connections, errors, __version__
from ._compat import bton
from ._compat import IS_PPC
from .workers import threadpool
from .makefile import MakeFile, StreamWriter

__all__ = (
    'HTTPRequest', 'HTTPConnection', 'HTTPServer',
    'KnownLengthRFile', 'ChunkedRFile',
    'Gateway', 'get_ssl_adapter_class',
)

IS_WINDOWS = platform.system() == 'Windows'
"""Flag indicating whether the app is running under Windows."""

IS_GAE = os.getenv('SERVER_SOFTWARE', '').startswith('Google App Engine/')
"""Flag indicating whether the app is running in GAE env.

Ref:
https://cloud.google.com/appengine/docs/standard/python/tools
/using-local-server#detecting_application_runtime_environment
"""

IS_UID_GID_RESOLVABLE = not IS_WINDOWS and not IS_GAE
"""Indicates whether UID/GID resolution's available under current platform."""

if IS_UID_GID_RESOLVABLE:
    try:
        import grp
        import pwd
    except ImportError:
        """Unavailable in the current env.

        This shouldn't be happening normally.
        All of the known cases are excluded via the if clause.
        """
        IS_UID_GID_RESOLVABLE = False
        grp, pwd = None, None
    import struct

if IS_WINDOWS and hasattr(socket, 'AF_INET6'):
    if not hasattr(socket, 'IPPROTO_IPV6'):
        socket.IPPROTO_IPV6 = 41
    if not hasattr(socket, 'IPV6_V6ONLY'):
        socket.IPV6_V6ONLY = 27

if not hasattr(socket, 'SO_PEERCRED'):
    """
    NOTE: the value for SO_PEERCRED can be architecture specific, in
    which case the getsockopt() will hopefully fail. The arch
    specific value could be derived from platform.processor()
    """
    socket.SO_PEERCRED = 21 if IS_PPC else 17

LF = b'\n'
CRLF = b'\r\n'
TAB = b'\t'
SPACE = b' '
COLON = b':'
SEMICOLON = b';'
EMPTY = b''
ASTERISK = b'*'
FORWARD_SLASH = b'/'
QUOTED_SLASH = b'%2F'
QUOTED_SLASH_REGEX = re.compile(b''.join((b'(?i)', QUOTED_SLASH)))

comma_separated_headers = [
    b'Accept', b'Accept-Charset', b'Accept-Encoding',
    b'Accept-Language', b'Accept-Ranges', b'Allow', b'Cache-Control',
    b'Connection', b'Content-Encoding', b'Content-Language', b'Expect',
    b'If-Match', b'If-None-Match', b'Pragma', b'Proxy-Authenticate', b'TE',
    b'Trailer', b'Transfer-Encoding', b'Upgrade', b'Vary', b'Via', b'Warning',
    b'WWW-Authenticate',
]

if not hasattr(logging, 'statistics'):
    logging.statistics = {}


class RFile(ABC):
    def __init__(self, rfile, wfile, conn):
        self.rfile = rfile
        self.wfile = wfile
        self.conn = conn

    def _send_100_if_needed(self):
        if not self.conn.they_are_waiting_for_100_continue:
            return

        mini_headers = ()
        go_ahead = h11.InformationalResponse(status_code=100, headers=mini_headers)
        bytes_out = self.conn.send(go_ahead)
        self.wfile.write(bytes_out)

    def _get_event(self):
        return self.conn.next_event()

    def _handle_input(self, data):
        self.conn.receive_data(data)
        evt = self._get_event()
        if isinstance(evt, h11.Data):
            return bytes(evt.data)
        else:
            return b''

    @abstractmethod
    def read(self, size=None):
        pass

    @abstractmethod
    def readline(self, size=None):
        pass

    @abstractmethod
    def readlines(self, sizehint=None):
        pass

    def close(self):
        self.rfile.close()


class KnownLengthRFile(RFile):
    """Wraps a file-like object, returning an empty string when exhausted.

    :param rfile: ``file`` of a known size
    :param int content_length: length of the file being read
    """

    def __init__(self, h_conn, rfile, wfile, content_length):
        """Initialize KnownLengthRFile instance."""
        super(KnownLengthRFile, self).__init__(rfile, wfile, h_conn)
        self.remaining = content_length

    def read(self, size=None):
        """Read a chunk from ``rfile`` buffer and return it.

        :param int size: amount of data to read

        :rtype: bytes
        :returns: chunk from ``rfile``, limited by size if specified
        """
        if self.remaining == 0:
            return b''
        if size is None:
            size = self.remaining
        else:
            size = min(size, self.remaining)
        self._send_100_if_needed()
        data = self.rfile.read(size)
        data = self._handle_input(data)
        self.remaining -= len(data)
        return data

    def readline(self, size=None):
        """Read a single line from ``rfile`` buffer and return it.

        :param int size: minimum amount of data to read

        :returns: one line from ``rfile``
        :rtype: bytes
        """
        if self.remaining == 0:
            return b''
        if size is None:
            size = self.remaining
        else:
            size = min(size, self.remaining)

        self._send_100_if_needed()
        data = self.rfile.readline(size)
        data = self._handle_input(data)
        self.remaining -= len(data)
        return data

    def readlines(self, sizehint=0):
        """Read all lines from ``rfile`` buffer and return them.

        :param int sizehint: hint of minimum amount of data to read

        :returns: lines of bytes read from ``rfile``
        :rtype: list[bytes]
        """
        # Shamelessly stolen from StringIO
        total = 0
        lines = []
        self._send_100_if_needed()
        line = self.readline(sizehint)
        while line:
            data = self._handle_input(line)
            lines.append(data)
            total += len(line)
            if 0 < sizehint <= total:
                break
            line = self.readline(sizehint)
        return lines

    def __iter__(self):
        """Return file iterator."""
        return self

    def __next__(self):
        """Generate next file chunk."""
        self._send_100_if_needed()
        data = next(self.rfile)
        data = self._handle_input(data)
        self.remaining -= len(data)
        return data

    next = __next__


class ChunkedRFile(RFile):
    """Wraps a file-like object, returning an empty string when exhausted.

    This class is intended to provide a conforming wsgi.input value for
    request entities that have been encoded with the 'chunked' transfer
    encoding.

    :param rfile: file encoded with the 'chunked' transfer encoding
    :param int maxlen: maximum length of the file being read
    :param int bufsize: size of the buffer used to read the file
    """

    def __init__(self, h_conn, rfile, wfile, maxlen, bufsize=8192):
        """Initialize ChunkedRFile instance."""
        super(ChunkedRFile, self).__init__(rfile, wfile, h_conn)
        self.maxlen = maxlen
        self.bytes_read = 0
        self.buffer = EMPTY
        self.bufsize = bufsize
        self.closed = False
        self.has_read_trailers = False

    def _read_trailers(self):
        end_states = (h11.DONE, h11.ERROR, h11.MUST_CLOSE, h11.CLOSED)
        while not self.has_read_trailers and self.conn.their_state not in end_states:
            line = self.rfile.readline()
            # TODO: We currently throw away trailing headers
            # This is currently in line with how cheroot handles trailers, but we should
            # create a way to return these back to the request object
            self._handle_input(line)
        self.has_read_trailers = True

    def _fetch(self):
        if self.closed:
            return

        self._send_100_if_needed()
        line = self.rfile.readline()

        # ignore handle_input output, since it won't return this data to us
        self._handle_input(line)

        self.bytes_read += len(line)

        if self.maxlen and self.bytes_read > self.maxlen:
            raise errors.MaxSizeExceeded(
                'Request Entity Too Large', self.maxlen,
            )

        line = line.strip().split(SEMICOLON, 1)

        try:
            chunk_size = line.pop(0)
            chunk_size = int(chunk_size, 16)
        except ValueError:
            raise ValueError(
                'Bad chunked transfer size: {chunk_size!r}'.
                    format(chunk_size=chunk_size),
            )

        if chunk_size <= 0:
            self._read_trailers()
            self.closed = True
            return

        if self.maxlen and self.bytes_read + chunk_size > self.maxlen:
            raise IOError('Request Entity Too Large')

        chunk = self.rfile.read(chunk_size)
        chunk = self._handle_input(chunk)
        self.bytes_read += len(chunk)
        self.buffer += chunk

        crlf = self.rfile.read(2)
        # see above ignore
        self._handle_input(crlf)
        if crlf != CRLF:
            raise ValueError(
                "Bad chunked transfer coding (expected '\\r\\n', "
                'got ' + repr(crlf) + ')',
            )

    def read(self, size=None):
        """Read a chunk from ``rfile`` buffer and return it.

        :param int size: amount of data to read

        :returns: chunk from ``rfile``, limited by size if specified
        :rtype: bytes
        """
        data = EMPTY

        if size == 0:
            return data

        while True:
            if size and len(data) >= size:
                return data

            if not self.buffer:
                self._fetch()
                if not self.buffer:
                    # EOF
                    return data

            if size:
                remaining = size - len(data)
                data += self.buffer[:remaining]
                self.buffer = self.buffer[remaining:]
            else:
                data += self.buffer
                self.buffer = EMPTY

    def readline(self, size=None):
        """Read a single line from ``rfile`` buffer and return it.

        :param int size: minimum amount of data to read

        :returns: one line from ``rfile``
        :rtype: bytes
        """
        data = EMPTY

        if size == 0:
            return data

        while True:
            if size and len(data) >= size:
                return data

            if not self.buffer:
                self._fetch()
                if not self.buffer:
                    # EOF
                    return data

            newline_pos = self.buffer.find(LF)
            if size:
                if newline_pos == -1:
                    remaining = size - len(data)
                    data += self.buffer[:remaining]
                    self.buffer = self.buffer[remaining:]
                else:
                    remaining = min(size - len(data), newline_pos)
                    data += self.buffer[:remaining]
                    self.buffer = self.buffer[remaining:]
            else:
                if newline_pos == -1:
                    data += self.buffer
                    self.buffer = EMPTY
                else:
                    data += self.buffer[:newline_pos]
                    self.buffer = self.buffer[newline_pos:]

    def readlines(self, sizehint=0):
        """Read all lines from ``rfile`` buffer and return them.

        :param int sizehint: hint of minimum amount of data to read

        :returns: lines of bytes read from ``rfile``
        :rtype: list[bytes]
        """
        # Shamelessly stolen from StringIO
        total = 0
        lines = []
        line = self.readline(sizehint)
        while line:
            lines.append(line)
            total += len(line)
            if 0 < sizehint <= total:
                break
            line = self.readline(sizehint)
        return lines

    def read_trailer_lines(self):
        """Read HTTP headers and yield them.

        Returns:
            Generator: yields CRLF separated lines.

        """
        if not self.closed:
            raise ValueError(
                'Cannot read trailers until the request body has been read.',
            )

        while True:
            line = self.rfile.readline()
            if not line:
                # No more data--illegal end of headers
                raise ValueError('Illegal end of headers.')

            self.bytes_read += len(line)
            if self.maxlen and self.bytes_read > self.maxlen:
                raise IOError('Request Entity Too Large')

            if line == CRLF:
                # Normal end of headers
                break
            if not line.endswith(CRLF):
                raise ValueError('HTTP requires CRLF terminators')

            yield line


class HTTPRequest:
    """An HTTP Request (and response).

    A single HTTP connection may consist of multiple request/response pairs.
    """

    server = None
    """The HTTPServer object which is receiving this request."""

    conn = None
    """The HTTPConnection object on which this request connected."""

    inheaders = {}
    """A dict of request headers."""

    outheaders = []
    """A list of header tuples to write in the response."""

    ready = False
    """When True, the request has been parsed and is ready to begin generating
    the response. When False, signals the calling Connection that the response
    should not be generated and the connection should close."""

    close_connection = False
    """Signals the calling Connection that the request should close. This does
    not imply an error! The client and/or server may each request that the
    connection be closed."""

    chunked_write = False
    """If True, output will be encoded with the "chunked" transfer-coding.

    This value is set automatically inside send_headers."""

    def __init__(self, server, conn, proxy_mode=False, strict_mode=True):
        """Initialize HTTP request container instance.

        :param server: web server object receiving this request
        :type server: HTTPServer
        :param conn: HTTP connection object for this request
        :type conn: HTTPConnection
        :param proxy_mode: whether this HTTPServer should behave as a PROXY
        :type proxy_mode: bool
        :param strict_mode: whether we should return a 400 Bad Request when
            we encounter a request that a HTTP compliant client should not be
            making
        :type strict_mode: bool
        """
        self.server = server
        self.conn = conn
        self.h_conn = h11.Connection(h11.SERVER)
        self.ready = False
        self.started_request = False
        self.scheme = b'http'
        if self.server.ssl_adapter is not None:
            self.scheme = b'https'
        # Use the lowest-common protocol in case read_request_line errors.
        self.response_protocol = 'HTTP/1.1'
        self.inheaders = {}

        self.status = ''
        self.outheaders = []
        self.sent_headers = False
        self.close_connection = self.__class__.close_connection
        self.chunked_read = False
        self.chunked_write = self.__class__.chunked_write
        self.proxy_mode = proxy_mode
        self.strict_mode = strict_mode

    def _process_next_h11_event(self, read_new=True):
        """Instruct h11 to process data in its buffer and return any events it has available.

        :param read_new: If the method should attempt to read new lines to find an event
        :type read_new: bool
        :return: An h11 event
        """
        # TODO: Determine if this wrapper is even needed. Apparently we don't
        # expect 100 at this point in the req cycle
        event = self.h_conn.next_event()
        while event is h11.NEED_DATA and read_new:
            if self.h_conn.they_are_waiting_for_100_continue:
                go_ahead = h11.InformationalResponse(status_code=100, headers=())
                bytes_out = self.h_conn.send(go_ahead)
                self.conn.wfile.write(bytes_out)
            line = self.conn.rfile.readline()
            self.h_conn.receive_data(line)
            event = self.h_conn.next_event()
        return event

    def parse_request(self):
        """Parse the next HTTP request start-line and message-headers."""
        try:
            req_line = self._process_next_h11_event()
            if isinstance(req_line, h11.Request):
                self.started_request = True
                self.uri = req_line.target
                scheme, authority, path, qs, fragment = urllib.parse.urlsplit(self.uri)  # noqa
                self.qs = qs
                self.method = req_line.method
                self.request_protocol = b'HTTP/%s' % req_line.http_version
                if req_line.http_version > b'1.1':
                    self.simple_response(505, 'Cannot fulfill request')
                self.response_protocol = b'HTTP/1.1'
                # TODO: oneliner-ify this
                self.inheaders = {}
                for header in req_line.headers:
                    self.inheaders[header[0]] = header[1]

                if (
                    b'transfer-encoding' in self.inheaders and
                    self.inheaders[b'transfer-encoding'].lower() == b'chunked'
                ):
                    self.chunked_read = True

                uri_is_absolute_form = scheme or authority

                if self.method == b'OPTIONS':
                    # TODO: cover this branch with tests
                    path = (
                        self.uri
                        # https://tools.ietf.org/html/rfc7230#section-5.3.4
                        if (self.proxy_mode and uri_is_absolute_form)
                        else path
                    )
                elif self.method == b'CONNECT':
                    # TODO: cover this branch with tests
                    if not self.proxy_mode:
                        self.simple_response(405)
                        return False

                    # `urlsplit()` above parses "example.com:3128" as path part
                    # of URI. This is a workaround, which makes it detect
                    # netloc correctly
                    uri_split = urllib.parse.urlsplit(b''.join((b'//', self.uri)))
                    _scheme, _authority, _path, _qs, _fragment = uri_split
                    _port = EMPTY
                    try:
                        _port = uri_split.port
                    except ValueError:
                        pass

                    # FIXME: use third-party validation to make checks against RFC
                    # the validation doesn't take into account, that urllib parses
                    # invalid URIs without raising errors
                    # https://tools.ietf.org/html/rfc7230#section-5.3.3
                    invalid_path = (
                            _authority != self.uri
                            or not _port
                            or any((_scheme, _path, _qs, _fragment))
                    )
                    if invalid_path:
                        self.simple_response(
                            400,
                            'Invalid path in Request-URI: request-'
                            'target must match authority-form.',
                        )
                        return False

                    authority = path = _authority
                    scheme = qs = fragment = EMPTY
                else:
                    disallowed_absolute = (
                            self.strict_mode
                            and not self.proxy_mode
                            and uri_is_absolute_form
                    )
                    if disallowed_absolute:
                        # https://tools.ietf.org/html/rfc7230#section-5.3.2
                        # (absolute form)
                        """Absolute URI is only allowed within proxies."""
                        self.simple_response(
                            400,
                            'Absolute URI not allowed'
                            ' if server is not a proxy.',
                        )
                        return False

                    invalid_path = (
                            self.strict_mode
                            and not self.uri.startswith(FORWARD_SLASH)
                            and not uri_is_absolute_form
                    )
                    if invalid_path:
                        # https://tools.ietf.org/html/rfc7230#section-5.3.1
                        # (origin_form) and
                        """Path should start with a forward slash."""
                        resp = (
                            'Invalid path in Request-URI: request-target must contain '
                            'origin-form which starts with absolute-path (URI '
                            'starting with a slash "/").'
                        )
                        self.simple_response(400, resp)
                        return False
                    try:
                        # TODO: Figure out whether exception can really happen here.
                        # It looks like it's caught on urlsplit() call above.
                        atoms = [
                            urllib.parse.unquote_to_bytes(x)
                            for x in QUOTED_SLASH_REGEX.split(path)
                        ]
                    except ValueError as ex:
                        self.simple_response(400, ex.args[0])
                        return False
                    path = QUOTED_SLASH.join(atoms)
                if fragment:
                    self.simple_response(
                        400,
                        'Illegal #fragment in Request-URI.',
                    )

                if not path.startswith(FORWARD_SLASH):
                    path = FORWARD_SLASH + path
                self.path = path
                self.authority = authority
                self.ready = True
            elif isinstance(req_line, h11.ConnectionClosed):
                self.close_connection = True
            else:
                # TODO
                raise NotImplementedError('Only expecting Request object here')
        except h11.RemoteProtocolError as e:
            err_map = {
                'bad Content-Length': 'Malformed Content-Length Header.',
                'illegal request line': 'Malformed Request-Line.',
                'illegal header line': 'Illegal header line.',
            }
            err_str = [v for k, v in err_map.items() if e.args[0] in k]
            err_str = str(e) if len(err_str) == 0 else err_str[0]
            self.simple_response(e.error_status_hint or 400, err_str)

    def respond(self):
        """Call the gateway and write its iterable output."""
        mrbs = self.server.max_request_body_size
        if self.chunked_read:
            self.rfile = ChunkedRFile(
                self.h_conn,
                self.conn.rfile, self.conn.wfile, mrbs,
            )
        else:
            cl = int(self.inheaders.get(b'content-length', 0))
            if mrbs and mrbs < cl:
                if not self.sent_headers:
                    self.simple_response(
                        '413 Request Entity Too Large',
                        'The entity sent with the request exceeds the '
                        'maximum allowed bytes.',
                    )
                return
            self.rfile = KnownLengthRFile(
                self.h_conn,
                self.conn.rfile, self.conn.wfile, cl,
            )

        if self.h_conn.client_is_waiting_for_100_continue:
            mini_headers = ()
            go_ahead = h11.InformationalResponse(
                status_code=100,
                headers=mini_headers,
            )
            bytes_out = self.h_conn.send(go_ahead)
            self.conn.wfile.write(bytes_out)
        try:
            self.server.gateway(self).respond()
            self.ready and self.ensure_headers_sent()
        except errors.MaxSizeExceeded as e:
            self.simple_response(413, 'Request Entity Too Large')
            self.close_connection = True
            return

        while (
            self.h_conn.their_state is h11.SEND_BODY
            and self.h_conn.our_state is not h11.ERROR
        ):
            data = self.rfile.read()
            self._process_next_h11_event(read_new=False)
            if data == EMPTY and self.h_conn.their_state is h11.SEND_BODY:
                # they didn't send a full body, kill connection,
                # set our state to ERROR
                self.h_conn.send_failed()

        # If we haven't sent our end-of-message data, send it now
        if self.h_conn.our_state not in (h11.DONE, h11.ERROR):
            bytes_out = self.h_conn.send(h11.EndOfMessage())
            self.conn.wfile.write(bytes_out)

        # prep for next req cycle if it's available
        if (
            self.h_conn.our_state is h11.DONE
            and self.h_conn.their_state is h11.DONE
        ):
            self.h_conn.start_next_cycle()
            self.close_connection = False
        else:
            # close connection if reuse unavailable
            self.close_connection = True

    def simple_response(self, status, msg=None):
        """Write a simple response back to the client."""
        if msg is None:
            msg = ''
        status = str(status)
        headers = [
            ('Content-Type', 'text/plain'),
        ]

        self.outheaders = headers
        self.status = status
        self.send_headers()
        if msg:
            self.write(bytes(msg, encoding='ascii'))

        evt = h11.EndOfMessage()
        bytes_out = self.h_conn.send(evt)
        self.conn.wfile.write(bytes_out)

    def ensure_headers_sent(self):
        """Ensure headers are sent to the client if not already sent."""
        if not self.sent_headers:
            self.sent_headers = True
            self.send_headers()

    def write(self, chunk):
        """Write unbuffered data to the client."""
        event = h11.Data(data=chunk)
        bytes_out = self.h_conn.send(event)
        self.conn.wfile.write(bytes_out)

    def send_headers(self):
        """Assert, process, and send the HTTP response message-headers.

        You must set ``self.status``, and :py:attr:`self.outheaders
        <HTTPRequest.outheaders>` before calling this.
        """
        hkeys = [key.lower() for key, value in self.outheaders]
        status = int(self.status[:3])

        if b'date' not in hkeys:
            self.outheaders.append((
                b'date',
                email.utils.formatdate(usegmt=True).encode('ISO-8859-1'),
            ))

        if b'server' not in hkeys:
            self.outheaders.append((
                b'server',
                self.server.server_name.encode('ISO-8859-1'),
            ))

        res = h11.Response(
            status_code=status, headers=self.outheaders,
            http_version=self.response_protocol[5:], reason=self.status[3:],
        )
        res_bytes = self.h_conn.send(res)
        self.conn.wfile.write(res_bytes)


class HTTPConnection:
    """An HTTP connection (active socket)."""

    remote_addr = None
    remote_port = None
    ssl_env = None
    rbufsize = io.DEFAULT_BUFFER_SIZE
    wbufsize = io.DEFAULT_BUFFER_SIZE
    RequestHandlerClass = HTTPRequest
    peercreds_enabled = False
    peercreds_resolve_enabled = False

    # Fields set by ConnectionManager.
    closeable = False
    last_used = None
    ready_with_data = False

    def __init__(self, server, sock, makefile=MakeFile):
        """Initialize HTTPConnection instance.

        Args:
            server (HTTPServer): web server object receiving this request
            sock (socket._socketobject): the raw socket object (usually
                TCP) for this connection
            makefile (file): a fileobject class for reading from the socket
        """
        self.server = server
        self.socket = sock
        self.rfile = makefile(sock, 'rb', self.rbufsize)
        self.wfile = makefile(sock, 'wb', self.wbufsize)
        self.requests_seen = 0

        self.peercreds_enabled = self.server.peercreds_enabled
        self.peercreds_resolve_enabled = self.server.peercreds_resolve_enabled

        # LRU cached methods:
        # Ref: https://stackoverflow.com/a/14946506/595220
        self.resolve_peer_creds = (
            lru_cache(maxsize=1)(self.resolve_peer_creds)
        )
        self.get_peer_creds = (
            lru_cache(maxsize=1)(self.get_peer_creds)
        )

    def communicate(self):
        """Read each request and respond appropriately.

        Returns true if the connection should be kept open.
        """
        request_seen = False
        try:
            req = self.RequestHandlerClass(self.server, self)
            req.parse_request()
            if self.server.stats['Enabled']:
                self.requests_seen += 1
            if not req.ready:
                # Something went wrong in the parsing (and the server has
                # probably already made a simple_response). Return and
                # let the conn close.
                return False

            request_seen = True
            req.respond()
            if not req.close_connection:
                return True
        except socket.error as ex:
            errnum = ex.args[0]
            # sadly SSL sockets return a different (longer) time out string
            timeout_errs = 'timed out', 'The read operation timed out'
            if errnum in timeout_errs:
                # Don't error if we're between requests; only error
                # if 1) no request has been started at all, or 2) we're
                # in the middle of a request.
                # See https://github.com/cherrypy/cherrypy/issues/853
                if (not request_seen) or (req and req.started_request):
                    self._conditional_error(req, '408 Request Timeout')
            elif errnum not in errors.socket_errors_to_ignore:
                self.server.error_log(
                    'socket.error %s' % repr(errnum),
                    level=logging.WARNING, traceback=True,
                )
                self._conditional_error(req, '500 Internal Server Error')
        except (KeyboardInterrupt, SystemExit):
            raise
        except errors.FatalSSLAlert:
            pass
        except errors.NoSSLError:
            self._handle_no_ssl(req)
        except Exception as ex:
            self.server.error_log(
                repr(ex), level=logging.ERROR, traceback=True,
            )
            self._conditional_error(req, '500 Internal Server Error')
        return False

    linger = False

    def _handle_no_ssl(self, req):
        if not req or req.sent_headers:
            return
        # Unwrap wfile
        try:
            resp_sock = self.socket._sock
        except AttributeError:
            # self.socket is of OpenSSL.SSL.Connection type
            resp_sock = self.socket._socket
        self.wfile = StreamWriter(resp_sock, 'wb', self.wbufsize)
        msg = (
            'The client sent a plain HTTP request, but '
            'this server only speaks HTTPS on this port.'
        )
        req.simple_response('400 Bad Request', msg)
        self.linger = True

    def _conditional_error(self, req, response):
        """Respond with an error.

        Don't bother writing if a response
        has already started being written.
        """
        if not req or req.sent_headers:
            return

        try:
            req.simple_response(response)
        except errors.FatalSSLAlert:
            pass
        except errors.NoSSLError:
            self._handle_no_ssl(req)

    def close(self):
        """Close the socket underlying this connection."""
        self.rfile.close()

        if not self.linger:
            self._close_kernel_socket()
            self.socket.close()
        else:
            # On the other hand, sometimes we want to hang around for a bit
            # to make sure the client has a chance to read our entire
            # response. Skipping the close() calls here delays the FIN
            # packet until the socket object is garbage-collected later.
            # Someday, perhaps, we'll do the full lingering_close that
            # Apache does, but not today.
            pass

    def get_peer_creds(self):  # LRU cached on per-instance basis, see __init__
        """Return the PID/UID/GID tuple of the peer socket for UNIX sockets.

        This function uses SO_PEERCRED to query the UNIX PID, UID, GID
        of the peer, which is only available if the bind address is
        a UNIX domain socket.

        Raises:
            NotImplementedError: in case of unsupported socket type
            RuntimeError: in case of SO_PEERCRED lookup unsupported or disabled

        """
        PEERCRED_STRUCT_DEF = '3i'

        if IS_WINDOWS or self.socket.family != socket.AF_UNIX:
            raise NotImplementedError(
                'SO_PEERCRED is only supported in Linux kernel and WSL',
            )
        elif not self.peercreds_enabled:
            raise RuntimeError(
                'Peer creds lookup is disabled within this server',
            )

        try:
            peer_creds = self.socket.getsockopt(
                # FIXME: Use LOCAL_CREDS for BSD-like OSs
                # Ref: https://gist.github.com/LucaFilipozzi/e4f1e118202aff27af6aadebda1b5d91  # noqa
                socket.SOL_SOCKET, socket.SO_PEERCRED,
                struct.calcsize(PEERCRED_STRUCT_DEF),
            )
        except socket.error as socket_err:
            """Non-Linux kernels don't support SO_PEERCRED.

            Refs:
            http://welz.org.za/notes/on-peer-cred.html
            https://github.com/daveti/tcpSockHack
            msdn.microsoft.com/en-us/commandline/wsl/release_notes#build-15025
            """
            six.raise_from(  # 3.6+: raise RuntimeError from socket_err
                RuntimeError,
                socket_err,
            )
        else:
            pid, uid, gid = struct.unpack(PEERCRED_STRUCT_DEF, peer_creds)
            return pid, uid, gid

    @property
    def peer_pid(self):
        """Return the id of the connected peer process."""
        pid, _, _ = self.get_peer_creds()
        return pid

    @property
    def peer_uid(self):
        """Return the user id of the connected peer process."""
        _, uid, _ = self.get_peer_creds()
        return uid

    @property
    def peer_gid(self):
        """Return the group id of the connected peer process."""
        _, _, gid = self.get_peer_creds()
        return gid

    def resolve_peer_creds(self):  # LRU cached on per-instance basis
        """Look up the username and group tuple of the ``PEERCREDS``.

        :returns: the username and group tuple of the ``PEERCREDS``

        :raises NotImplementedError: if the OS is unsupported
        :raises RuntimeError: if UID/GID lookup is unsupported or disabled
        """
        if not IS_UID_GID_RESOLVABLE:
            raise NotImplementedError(
                'UID/GID lookup is unavailable under current platform. '
                'It can only be done under UNIX-like OS '
                'but not under the Google App Engine',
            )
        elif not self.peercreds_resolve_enabled:
            raise RuntimeError(
                'UID/GID lookup is disabled within this server',
            )

        user = pwd.getpwuid(self.peer_uid).pw_name  # [0]
        group = grp.getgrgid(self.peer_gid).gr_name  # [0]

        return user, group

    @property
    def peer_user(self):
        """Return the username of the connected peer process."""
        user, _ = self.resolve_peer_creds()
        return user

    @property
    def peer_group(self):
        """Return the group of the connected peer process."""
        _, group = self.resolve_peer_creds()
        return group

    def _close_kernel_socket(self):
        """Close kernel socket in outdated Python versions.

        On old Python versions,
        Python's socket module does NOT call close on the kernel
        socket when you call socket.close(). We do so manually here
        because we want this server to send a FIN TCP segment
        immediately. Note this must be called *before* calling
        socket.close(), because the latter drops its reference to
        the kernel socket.
        """
        if six.PY2 and hasattr(self.socket, '_sock'):
            self.socket._sock.close()


class HTTPServer:
    """An HTTP server."""

    _bind_addr = '127.0.0.1'
    _interrupt = None

    gateway = None
    """A Gateway instance."""

    minthreads = None
    """The minimum number of worker threads to create (default 10)."""

    maxthreads = None
    """The maximum number of worker threads to create.

    (default -1 = no limit)"""

    server_name = None
    """The name of the server; defaults to ``self.version``."""

    protocol = 'HTTP/1.1'
    """The version string to write in the Status-Line of all HTTP responses.

    For example, "HTTP/1.1" is the default. This also limits the supported
    features used in the response."""

    request_queue_size = 5
    """The 'backlog' arg to socket.listen(); max queued connections.

    (default 5)."""

    shutdown_timeout = 5
    """The total time to wait for worker threads to cleanly exit.

    Specified in seconds."""

    timeout = 10
    """The timeout in seconds for accepted connections (default 10)."""

    version = 'Cheroot/{version!s}'.format(version=__version__)
    """A version string for the HTTPServer."""

    software = None
    """The value to set for the SERVER_SOFTWARE entry in the WSGI environ.

    If None, this defaults to ``'%s Server' % self.version``.
    """

    ready = False
    """Internal flag which indicating the socket is accepting connections."""

    max_request_header_size = 0
    """The maximum size, in bytes, for request headers, or 0 for no limit."""

    max_request_body_size = 0
    """The maximum size, in bytes, for request bodies, or 0 for no limit."""

    nodelay = True
    """If True (the default since 3.1), sets the TCP_NODELAY socket option."""

    ConnectionClass = HTTPConnection
    """The class to use for handling HTTP connections."""

    ssl_adapter = None
    """An instance of ``ssl.Adapter`` (or a subclass).

    Ref: :py:class:`ssl.Adapter <cheroot.ssl.Adapter>`.

    You must have the corresponding TLS driver library installed.
    """

    peercreds_enabled = False
    """
    If :py:data:`True`, peer creds will be looked up via UNIX domain socket.
    """

    peercreds_resolve_enabled = False
    """
    If :py:data:`True`, username/group will be looked up in the OS from
    ``PEERCREDS``-provided IDs.
    """

    keep_alive_conn_limit = 10
    """The maximum number of waiting keep-alive connections that will be kept open.

    Default is 10. Set to None to have unlimited connections."""

    def __init__(
            self, bind_addr, gateway,
            minthreads=1, maxthreads=1, server_name=None,
            peercreds_enabled=False, peercreds_resolve_enabled=False,
    ):
        """Initialize HTTPServer instance.

        Args:
            bind_addr (tuple): network interface to listen to
            gateway (Gateway): gateway for processing HTTP requests
            minthreads (int): minimum number of threads for HTTP thread pool
            maxthreads (int): maximum number of threads for HTTP thread pool
            server_name (str): web server name to be advertised via Server
                HTTP header
        """
        self.bind_addr = bind_addr
        self.gateway = gateway

        self.requests = threadpool.ThreadPool(
            self, min=minthreads or 1, max=maxthreads,
        )
        self.connections = connections.ConnectionManager(self)

        if not server_name:
            server_name = self.version
        self.server_name = server_name
        self.peercreds_enabled = peercreds_enabled
        self.peercreds_resolve_enabled = (
                peercreds_resolve_enabled and peercreds_enabled
        )
        self.clear_stats()

    def clear_stats(self):
        """Reset server stat counters.."""
        self._start_time = None
        self._run_time = 0
        self.stats = {
            'Enabled': False,
            'Bind Address': lambda s: repr(self.bind_addr),
            'Run time': lambda s: (not s['Enabled']) and -1 or self.runtime(),
            'Accepts': 0,
            'Accepts/sec': lambda s: s['Accepts'] / self.runtime(),
            'Queue': lambda s: getattr(self.requests, 'qsize', None),
            'Threads': lambda s: len(getattr(self.requests, '_threads', [])),
            'Threads Idle': lambda s: getattr(self.requests, 'idle', None),
            'Socket Errors': 0,
            'Requests': lambda s: (not s['Enabled']) and -1 or sum(
                [w['Requests'](w) for w in s['Worker Threads'].values()], 0,
            ),
            'Bytes Read': lambda s: (not s['Enabled']) and -1 or sum(
                [w['Bytes Read'](w) for w in s['Worker Threads'].values()], 0,
            ),
            'Bytes Written': lambda s: (not s['Enabled']) and -1 or sum(
                [w['Bytes Written'](w) for w in s['Worker Threads'].values()],
                0,
            ),
            'Work Time': lambda s: (not s['Enabled']) and -1 or sum(
                [w['Work Time'](w) for w in s['Worker Threads'].values()], 0,
            ),
            'Read Throughput': lambda s: (not s['Enabled']) and -1 or sum(
                [w['Bytes Read'](w) / (w['Work Time'](w) or 1e-6)
                 for w in s['Worker Threads'].values()], 0,
            ),
            'Write Throughput': lambda s: (not s['Enabled']) and -1 or sum(
                [w['Bytes Written'](w) / (w['Work Time'](w) or 1e-6)
                 for w in s['Worker Threads'].values()], 0,
            ),
            'Worker Threads': {},
        }
        logging.statistics['Cheroot HTTPServer %d' % id(self)] = self.stats

    def runtime(self):
        """Return server uptime."""
        if self._start_time is None:
            return self._run_time
        else:
            return self._run_time + (time.time() - self._start_time)

    def __str__(self):
        """Render Server instance representing bind address."""
        return '%s.%s(%r)' % (
            self.__module__, self.__class__.__name__,
            self.bind_addr,
        )

    @property
    def bind_addr(self):
        """Return the interface on which to listen for connections.

        For TCP sockets, a (host, port) tuple. Host values may be any
        :term:`IPv4` or :term:`IPv6` address, or any valid hostname.
        The string 'localhost' is a synonym for '127.0.0.1' (or '::1',
        if your hosts file prefers :term:`IPv6`).
        The string '0.0.0.0' is a special :term:`IPv4` entry meaning
        "any active interface" (INADDR_ANY), and '::' is the similar
        IN6ADDR_ANY for :term:`IPv6`.
        The empty string or :py:data:`None` are not allowed.

        For UNIX sockets, supply the file name as a string.

        Systemd socket activation is automatic and doesn't require tempering
        with this variable.

        .. glossary::

           :abbr:`IPv4 (Internet Protocol version 4)`
              Internet Protocol version 4

           :abbr:`IPv6 (Internet Protocol version 6)`
              Internet Protocol version 6
        """
        return self._bind_addr

    @bind_addr.setter
    def bind_addr(self, value):
        """Set the interface on which to listen for connections."""
        if isinstance(value, tuple) and value[0] in ('', None):
            # Despite the socket module docs, using '' does not
            # allow AI_PASSIVE to work. Passing None instead
            # returns '0.0.0.0' like we want. In other words:
            #     host    AI_PASSIVE     result
            #      ''         Y         192.168.x.y
            #      ''         N         192.168.x.y
            #     None        Y         0.0.0.0
            #     None        N         127.0.0.1
            # But since you can get the same effect with an explicit
            # '0.0.0.0', we deny both the empty string and None as values.
            raise ValueError(
                "Host values of '' or None are not allowed. "
                "Use '0.0.0.0' (IPv4) or '::' (IPv6) instead "
                'to listen on all active interfaces.',
            )
        self._bind_addr = value

    def safe_start(self):
        """Run the server forever, and stop it cleanly on exit."""
        try:
            self.start()
        except (KeyboardInterrupt, IOError):
            # The time.sleep call might raise
            # "IOError: [Errno 4] Interrupted function call" on KBInt.
            self.error_log('Keyboard Interrupt: shutting down')
            self.stop()
            raise
        except SystemExit:
            self.error_log('SystemExit raised: shutting down')
            self.stop()
            raise

    def prepare(self):
        """Prepare server to serving requests.

        It binds a socket's port, setups the socket to ``listen()`` and does
        other preparing things.
        """
        self._interrupt = None

        if self.software is None:
            self.software = '%s Server' % self.version

        # Select the appropriate socket
        self.socket = None
        msg = 'No socket could be created'
        if os.getenv('LISTEN_PID', None):
            # systemd socket activation
            self.socket = socket.fromfd(3, socket.AF_INET, socket.SOCK_STREAM)
        elif isinstance(self.bind_addr, (six.text_type, six.binary_type)):
            # AF_UNIX socket
            try:
                self.bind_unix_socket(self.bind_addr)
            except socket.error as serr:
                msg = '%s -- (%s: %s)' % (msg, self.bind_addr, serr)
                six.raise_from(socket.error(msg), serr)
        else:
            # AF_INET or AF_INET6 socket
            # Get the correct address family for our host (allows IPv6
            # addresses)
            host, port = self.bind_addr
            try:
                info = socket.getaddrinfo(
                    host, port, socket.AF_UNSPEC,
                    socket.SOCK_STREAM, 0, socket.AI_PASSIVE,
                )
            except socket.gaierror:
                sock_type = socket.AF_INET
                bind_addr = self.bind_addr

                if ':' in host:
                    sock_type = socket.AF_INET6
                    bind_addr = bind_addr + (0, 0)

                info = [(sock_type, socket.SOCK_STREAM, 0, '', bind_addr)]

            for res in info:
                af, socktype, proto, canonname, sa = res
                try:
                    self.bind(af, socktype, proto)
                    break
                except socket.error as serr:
                    msg = '%s -- (%s: %s)' % (msg, sa, serr)
                    if self.socket:
                        self.socket.close()
                    self.socket = None

        if not self.socket:
            raise socket.error(msg)

        # Timeout so KeyboardInterrupt can be caught on Win32
        self.socket.settimeout(1)
        self.socket.listen(self.request_queue_size)

        # Create worker threads
        self.requests.start()

        self.ready = True
        self._start_time = time.time()

    def serve(self):
        """Serve requests, after invoking :func:`prepare()`."""
        while self.ready:
            try:
                self.tick()
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception:
                self.error_log(
                    'Error in HTTPServer.tick', level=logging.ERROR,
                    traceback=True,
                )

            if self.interrupt:
                while self.interrupt is True:
                    # Wait for self.stop() to complete. See _set_interrupt.
                    time.sleep(0.1)
                if self.interrupt:
                    raise self.interrupt

    def start(self):
        """Run the server forever.

        It is shortcut for invoking :func:`prepare()` then :func:`serve()`.
        """
        # We don't have to trap KeyboardInterrupt or SystemExit here,
        # because cherrypy.server already does so, calling self.stop() for us.
        # If you're using this server with another framework, you should
        # trap those exceptions in whatever code block calls start().
        self.prepare()
        self.serve()

    def error_log(self, msg='', level=20, traceback=False):
        """Write error message to log.

        Args:
            msg (str): error message
            level (int): logging level
            traceback (bool): add traceback to output or not
        """
        # Override this in subclasses as desired
        sys.stderr.write('{msg!s}\n'.format(msg=msg))
        sys.stderr.flush()
        if traceback:
            tblines = traceback_.format_exc()
            sys.stderr.write(tblines)
            sys.stderr.flush()

    def bind(self, family, type, proto=0):
        """Create (or recreate) the actual socket object."""
        sock = self.prepare_socket(
            self.bind_addr,
            family, type, proto,
            self.nodelay, self.ssl_adapter,
        )
        sock = self.socket = self.bind_socket(sock, self.bind_addr)
        self.bind_addr = self.resolve_real_bind_addr(sock)
        return sock

    def bind_unix_socket(self, bind_addr):
        """Create (or recreate) a UNIX socket object."""
        if IS_WINDOWS:
            """
            Trying to access socket.AF_UNIX under Windows
            causes an AttributeError.
            """
            raise ValueError(  # or RuntimeError?
                'AF_UNIX sockets are not supported under Windows.',
            )

        fs_permissions = 0o777  # TODO: allow changing mode

        try:
            # Make possible reusing the socket...
            os.unlink(self.bind_addr)
        except OSError:
            """
            File does not exist, which is the primary goal anyway.
            """
        except TypeError as typ_err:
            err_msg = str(typ_err)
            if (
                    'remove() argument 1 must be encoded '
                    'string without null bytes, not unicode'
                    not in err_msg
                    and 'embedded NUL character' not in err_msg  # py34
                    and 'argument must be a '
                        'string without NUL characters' not in err_msg  # pypy2
            ):
                raise
        except ValueError as val_err:
            err_msg = str(val_err)
            if (
                    'unlink: embedded null '
                    'character in path' not in err_msg
                    and 'embedded null byte' not in err_msg
                    and 'argument must be a '
                        'string without NUL characters' not in err_msg  # pypy3
            ):
                raise

        sock = self.prepare_socket(
            bind_addr=bind_addr,
            family=socket.AF_UNIX, type=socket.SOCK_STREAM, proto=0,
            nodelay=self.nodelay, ssl_adapter=self.ssl_adapter,
        )

        try:
            """Linux way of pre-populating fs mode permissions."""
            # Allow everyone access the socket...
            os.fchmod(sock.fileno(), fs_permissions)
            FS_PERMS_SET = True
        except OSError:
            FS_PERMS_SET = False

        try:
            sock = self.bind_socket(sock, bind_addr)
        except socket.error:
            sock.close()
            raise

        bind_addr = self.resolve_real_bind_addr(sock)

        try:
            """FreeBSD/macOS pre-populating fs mode permissions."""
            if not FS_PERMS_SET:
                try:
                    os.lchmod(bind_addr, fs_permissions)
                except AttributeError:
                    os.chmod(bind_addr, fs_permissions, follow_symlinks=False)
                FS_PERMS_SET = True
        except OSError:
            pass

        if not FS_PERMS_SET:
            self.error_log(
                'Failed to set socket fs mode permissions',
                level=logging.WARNING,
            )

        self.bind_addr = bind_addr
        self.socket = sock
        return sock

    @staticmethod
    def prepare_socket(bind_addr, family, type, proto, nodelay, ssl_adapter):
        """Create and prepare the socket object."""
        sock = socket.socket(family, type, proto)
        connections.prevent_socket_inheritance(sock)

        host, port = bind_addr[:2]
        IS_EPHEMERAL_PORT = port == 0

        if not (IS_WINDOWS or IS_EPHEMERAL_PORT):
            """Enable SO_REUSEADDR for the current socket.

            Skip for Windows (has different semantics)
            or ephemeral ports (can steal ports from others).

            Refs:
            * https://msdn.microsoft.com/en-us/library/ms740621(v=vs.85).aspx
            * https://github.com/cherrypy/cheroot/issues/114
            * https://gavv.github.io/blog/ephemeral-port-reuse/
            """
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if nodelay and not isinstance(
                bind_addr,
                (six.text_type, six.binary_type),
        ):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        if ssl_adapter is not None:
            sock = ssl_adapter.bind(sock)

        # If listening on the IPV6 any address ('::' = IN6ADDR_ANY),
        # activate dual-stack. See
        # https://github.com/cherrypy/cherrypy/issues/871.
        listening_ipv6 = (
                hasattr(socket, 'AF_INET6')
                and family == socket.AF_INET6
                and host in ('::', '::0', '::0.0.0.0')
        )
        if listening_ipv6:
            try:
                sock.setsockopt(
                    socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0,
                )
            except (AttributeError, socket.error):
                # Apparently, the socket option is not available in
                # this machine's TCP stack
                pass

        return sock

    @staticmethod
    def bind_socket(socket_, bind_addr):
        """Bind the socket to given interface."""
        socket_.bind(bind_addr)
        return socket_

    @staticmethod
    def resolve_real_bind_addr(socket_):
        """Retrieve actual bind address from bound socket."""
        # FIXME: keep requested bind_addr separate real bound_addr (port
        # is different in case of ephemeral port 0)
        bind_addr = socket_.getsockname()
        if socket_.family in (
                # Windows doesn't have socket.AF_UNIX, so not using it in check
                socket.AF_INET,
                socket.AF_INET6,
        ):
            """UNIX domain sockets are strings or bytes.

            In case of bytes with a leading null-byte it's an abstract socket.
            """
            return bind_addr[:2]

        if isinstance(bind_addr, six.binary_type):
            bind_addr = bton(bind_addr)

        return bind_addr

    def tick(self):
        """Accept a new connection and put it on the Queue."""
        if not self.ready:
            return

        conn = self.connections.get_conn(self.socket)
        if conn:
            try:
                self.requests.put(conn)
            except queue.Full:
                # Just drop the conn. TODO: write 503 back?
                conn.close()

        self.connections.expire()

    @property
    def interrupt(self):
        """Flag interrupt of the server."""
        return self._interrupt

    @interrupt.setter
    def interrupt(self, interrupt):
        """Perform the shutdown of this server and save the exception."""
        self._interrupt = True
        self.stop()
        self._interrupt = interrupt

    def stop(self):
        """Gracefully shutdown a server that is serving forever."""
        self.ready = False
        if self._start_time is not None:
            self._run_time += (time.time() - self._start_time)
        self._start_time = None

        sock = getattr(self, 'socket', None)
        if sock:
            if not isinstance(
                    self.bind_addr,
                    (six.text_type, six.binary_type),
            ):
                # Touch our own socket to make accept() return immediately.
                try:
                    host, port = sock.getsockname()[:2]
                except socket.error as ex:
                    if ex.args[0] not in errors.socket_errors_to_ignore:
                        # Changed to use error code and not message
                        # See
                        # https://github.com/cherrypy/cherrypy/issues/860.
                        raise
                else:
                    # Note that we're explicitly NOT using AI_PASSIVE,
                    # here, because we want an actual IP to touch.
                    # localhost won't work if we've bound to a public IP,
                    # but it will if we bound to '0.0.0.0' (INADDR_ANY).
                    for res in socket.getaddrinfo(
                            host, port, socket.AF_UNSPEC,
                            socket.SOCK_STREAM,
                    ):
                        af, socktype, proto, canonname, sa = res
                        s = None
                        try:
                            s = socket.socket(af, socktype, proto)
                            # See
                            # https://groups.google.com/group/cherrypy-users/
                            #     browse_frm/thread/bbfe5eb39c904fe0
                            s.settimeout(1.0)
                            s.connect((host, port))
                            s.close()
                        except socket.error:
                            if s:
                                s.close()
            if hasattr(sock, 'close'):
                sock.close()
            self.socket = None

        self.connections.close()
        self.requests.stop(self.shutdown_timeout)


class Gateway:
    """Base class to interface HTTPServer with other systems, such as WSGI."""

    def __init__(self, req):
        """Initialize Gateway instance with request.

        Args:
            req (HTTPRequest): current HTTP request
        """
        self.req = req

    def respond(self):
        """Process the current request. Must be overridden in a subclass."""
        raise NotImplementedError  # pragma: no cover


# These may either be ssl.Adapter subclasses or the string names
# of such classes (in which case they will be lazily loaded).
ssl_adapters = {
    'builtin': 'cheroot.ssl.builtin.BuiltinSSLAdapter',
    'pyopenssl': 'cheroot.ssl.pyopenssl.pyOpenSSLAdapter',
}


def get_ssl_adapter_class(name='builtin'):
    """Return an SSL adapter class for the given name."""
    adapter = ssl_adapters[name.lower()]
    if isinstance(adapter, six.string_types):
        last_dot = adapter.rfind('.')
        attr_name = adapter[last_dot + 1:]
        mod_path = adapter[:last_dot]

        try:
            mod = sys.modules[mod_path]
            if mod is None:
                raise KeyError()
        except KeyError:
            # The last [''] is important.
            mod = __import__(mod_path, globals(), locals(), [''])

        # Let an AttributeError propagate outward.
        try:
            adapter = getattr(mod, attr_name)
        except AttributeError:
            raise AttributeError("'%s' object has no attribute '%s'"
                                 % (mod_path, attr_name))

    return adapter
