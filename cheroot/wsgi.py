"""WSGI gateways for the Cheroot HTTP server."""

import sys

from cheroot.server import HTTPServer, Gateway
from cheroot.compat import basestring, ntob, ntou, tonative, py3k, unicodestr


class WSGIServer(HTTPServer):
    """A subclass of HTTPServer which calls a WSGI application."""

    def __init__(self, bind_addr, gateway=None, **kwargs):
        self.wsgi_app = kwargs.pop("wsgi_app", None)
        if gateway is None:
            gateway = WSGIGateway_10
        HTTPServer.__init__(self, bind_addr, gateway=gateway, **kwargs)


class WSGIGateway(Gateway):
    """A base class to interface HTTPServer with WSGI."""

    def __init__(self, req):
        self.req = req
        self.started_response = False
        self.env = self.get_environ()
        self.remaining_bytes_out = None

    def get_environ(self):
        """Return a new environ dict targeting the given wsgi.version"""
        raise NotImplemented

    def respond(self):
        """Process the current request."""
        response = self.req.server.wsgi_app(self.env, self.start_response)
        try:
            for chunk in response:
                # "The start_response callable must not actually transmit
                # the response headers. Instead, it must store them for the
                # server or gateway to transmit only after the first
                # iteration of the application return value that yields
                # a NON-EMPTY string, or upon the application's first
                # invocation of the write() callable." (PEP 333)
                if chunk:
                    if isinstance(chunk, unicodestr):
                        chunk = chunk.encode('ISO-8859-1')
                    self.write(chunk)
        finally:
            if hasattr(response, "close"):
                response.close()

    def start_response(self, status, headers, exc_info=None):
        """WSGI callable to begin the HTTP response."""
        # "The application may call start_response more than once,
        # if and only if the exc_info argument is provided."
        if self.started_response and not exc_info:
            raise AssertionError("WSGI start_response called a second "
                                 "time with no exc_info.")
        self.started_response = True

        # "if exc_info is provided, and the HTTP headers have already been
        # sent, start_response must raise an error, and should raise the
        # exc_info tuple."
        if (exc_info is not None) and self.req.sent_headers:
            try:
                if py3k:
                    raise exc_info[0](exc_info[1]).with_traceback(exc_info[2])
                else:
                    raise (exc_info[0], exc_info[1], exc_info[2])
            finally:
                exc_info = None

        # According to PEP 3333, when using Python 3, the response status
        # and headers must be bytes masquerading as unicode; that is, they
        # must be of type "str" but are restricted to code points in the
        # "latin-1" set.
        if not isinstance(status, str):
            raise TypeError("WSGI response status is not of type str.")
        self.req.status = ntob(status)

        for k, v in headers:
            if not isinstance(k, str):
                raise TypeError(
                    "WSGI response header key %s is not of type str." %
                    repr(k))
            if not isinstance(v, str):
                raise TypeError(
                    "WSGI response header value %s is not of type str." %
                    repr(v))
            if k.lower() == 'content-length':
                self.remaining_bytes_out = int(v)
            self.req.outheaders.append((ntob(k), ntob(v)))

        return self.write

    def write(self, chunk):
        """WSGI callable to write unbuffered data to the client.

        This method is also used internally by start_response (to write
        data from the iterable returned by the WSGI application).
        """
        if not self.started_response:
            raise AssertionError("WSGI write called before start_response.")

        chunklen = len(chunk)
        rbo = self.remaining_bytes_out
        if rbo is not None and chunklen > rbo:
            if not self.req.sent_headers:
                # Whew. We can send a 500 to the client.
                self.req.simple_response(
                    "500 Internal Server Error",
                    "The requested resource returned more bytes than the "
                    "declared Content-Length.")
            else:
                # Dang. We have probably already sent data. Truncate the chunk
                # to fit (so the client doesn't hang) and raise an error later.
                chunk = chunk[:rbo]

        if not self.req.sent_headers:
            self.req.sent_headers = True
            self.req.send_headers()

        if self.req.allow_message_body:
            self.req.write(chunk)

        if rbo is not None:
            rbo -= chunklen
            if rbo < 0:
                raise ValueError(
                    "Response body exceeds the declared Content-Length.")


class WSGIGateway_10(WSGIGateway):
    """A Gateway class to interface HTTPServer with WSGI 1.0.x."""

    def get_environ(self):
        """Return a new environ dict targeting the given wsgi.version"""
        req = self.req
        env = {
            # set a non-standard environ entry so the WSGI app can know what
            # the *real* server protocol is (and what features to support).
            # See http://www.faqs.org/rfcs/rfc2145.html.
            'ACTUAL_SERVER_PROTOCOL': req.server.protocol,
            'PATH_INFO': tonative(req.path),
            'QUERY_STRING': tonative(req.qs),
            'REMOTE_ADDR': req.conn.remote_addr or '',
            'REMOTE_PORT': str(req.conn.remote_port or ''),
            'REQUEST_METHOD': tonative(req.method),
            'REQUEST_URI': req.uri,
            'SCRIPT_NAME': '',
            'SERVER_NAME': req.server.server_name,
            # Bah. "SERVER_PROTOCOL" is actually the REQUEST protocol.
            'SERVER_PROTOCOL': tonative(req.request_protocol),
            'SERVER_SOFTWARE': req.server.software,
            'wsgi.errors': sys.stderr,
            'wsgi.input': req.rfile,
            'wsgi.multiprocess': False,
            'wsgi.multithread': True,
            'wsgi.run_once': False,
            'wsgi.url_scheme': tonative(req.scheme),
            'wsgi.version': (1, 0),
        }

        if isinstance(req.server.bind_addr, basestring):
            # AF_UNIX. This isn't really allowed by WSGI, which doesn't
            # address unix domain sockets. But it's better than nothing.
            env["SERVER_PORT"] = ""
        else:
            env["SERVER_PORT"] = str(req.server.bind_addr[1])

        # Request headers
        for k, v in req.inheaders.items():
            k = tonative(k).upper().replace("-", "_")
            env["HTTP_" + k] = tonative(v)

        # CONTENT_TYPE/CONTENT_LENGTH
        ct = env.pop("HTTP_CONTENT_TYPE", None)
        if ct is not None:
            env["CONTENT_TYPE"] = ct
        cl = env.pop("HTTP_CONTENT_LENGTH", None)
        if cl is not None:
            env["CONTENT_LENGTH"] = cl

        if req.conn.ssl_env:
            env.update(req.conn.ssl_env)

        return env


class WSGIGateway_u0(WSGIGateway_10):
    """A Gateway class to interface HTTPServer with WSGI u.0.

    WSGI u.0 is an experimental protocol, which uses unicode for keys and
    values in both Python 2 and Python 3.
    """

    def get_environ(self):
        """Return a new environ dict targeting the given wsgi.version"""
        req = self.req
        env_10 = WSGIGateway_10.get_environ(self)
        env = env_10.copy()
        env[u'wsgi.version'] = ('u', 0)

        # Request-URI
        env.setdefault(u'wsgi.url_encoding', u'utf-8')
        try:
            if py3k:
                for key in ["PATH_INFO", "SCRIPT_NAME", "QUERY_STRING"]:
                    # Re-encode since our "decoded" string is just
                    # bytes masquerading as unicode via Latin-1
                    val = env_10[key].encode('ISO-8859-1')
                    # ...now decode according to the configured encoding
                    env[key] = val.decode(env['wsgi.url_encoding'])
            else:
                # SCRIPT_NAME is the empty string, who cares what encoding it
                # is?
                env["PATH_INFO"] = req.path.decode(env['wsgi.url_encoding'])
                env["QUERY_STRING"] = req.qs.decode(env['wsgi.url_encoding'])
        except UnicodeDecodeError:
            # Fall back to latin 1 so apps can transcode if needed.
            env[u'wsgi.url_encoding'] = u'ISO-8859-1'
            for key in [u"PATH_INFO", u"SCRIPT_NAME", u"QUERY_STRING"]:
                if py3k:
                    env[key] = env_10[key]
                else:
                    env[key] = env_10[str(key)].decode(
                        env['wsgi.url_encoding'])

        if not py3k:
            for k, v in env.items():
                if (
                    isinstance(v, str) and
                    k not in ('REQUEST_URI', 'wsgi.input')
                ):
                    env[k] = ntou(v)

        return env


class WSGIPathInfoDispatcher(object):
    """A WSGI dispatcher for dispatch based on the PATH_INFO.

    apps: a dict or list of (path_prefix, app) pairs.
    """

    def __init__(self, apps):
        try:
            apps = list(apps.items())
        except AttributeError:
            pass

        # Sort the apps by len(path), descending
        if py3k:
            apps.sort()
        else:
            apps.sort(lambda x, y: cmp(len(x[0]), len(y[0])))
        apps.reverse()

        # The path_prefix strings must start, but not end, with a slash.
        # Use "" instead of "/".
        self.apps = [(p.rstrip("/"), a) for p, a in apps]

    def __call__(self, environ, start_response):
        path = environ["PATH_INFO"] or "/"
        for p, app in self.apps:
            # The apps list should be sorted by length, descending.
            if path.startswith(p + "/") or path == p:
                environ = environ.copy()
                environ["SCRIPT_NAME"] = environ["SCRIPT_NAME"] + p
                environ["PATH_INFO"] = path[len(p):]
                return app(environ, start_response)

        start_response('404 Not Found', [('Content-Type', 'text/plain'),
                                         ('Content-Length', '0')])
        return ['']
