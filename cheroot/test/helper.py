"""A library of helper functions for the Cheroot test suite."""

import datetime
import os
thisdir = os.path.abspath(os.path.dirname(__file__))
serverpem = os.path.join(os.getcwd(), thisdir, 'test.pem')

import socket
import sys
import time
import threading
from traceback import format_exc

from cheroot.compat import basestring, HTTPConnection
from cheroot.compat import HTTPSConnection, ntob
from cheroot import server, ssllib, wsgi
from cheroot.test import webtest

import nose

config = {
    'protocol': "HTTP/1.1",
    'bind_addr': ('127.0.0.1', 54583),
    'server': 'wsgi',
}
try:
    import testconfig
    if testconfig.config is not None:
        config.update(testconfig.config)
except ImportError:
    pass


class CherootWebCase(webtest.WebCase):

    available_servers = {'wsgi': wsgi.WSGIServer,
                         'native': server.HTTPServer,
                         }
    default_server = "wsgi"
    httpserver_startup_timeout = 5

    def setup_class(cls):
        """Create and run one HTTP server per class."""
        conf = config.copy()
        if hasattr(cls, "config"):
            conf.update(cls.config)

        sclass = conf.pop('server', 'wsgi')
        server_factory = cls.available_servers.get(sclass)
        if server_factory is None:
            raise RuntimeError('Unknown server in config: %s' % sclass)
        cls.httpserver = server_factory(**conf)

        if isinstance(cls.httpserver.bind_addr, basestring):
            cls.HTTP_CONN = UnixSocketHTTPConnection(cls.httpserver.bind_addr)
        else:
            cls.HOST, cls.PORT = cls.httpserver.bind_addr
            if cls.httpserver.ssl_adapter is None:
                cls.HTTP_CONN = HTTPConnection
                cls.scheme = 'http'
            else:
                cls.HTTP_CONN = HTTPSConnection
                cls.scheme = 'https'

        # Override the server error_log method so we can test writes to it.
        def logsink(msg="", level=20, traceback=False):
            if traceback:
                traceback = format_exc()
            cls.log.append((msg, level, traceback))
            #print(msg, level, traceback)
        cls.log = []
        cls.httpserver.error_log = logsink

        # Turn on stats, mostly for code coverage
        cls.httpserver.stats['Enabled'] = True

        if hasattr(cls, 'setup_server'):
            # Clear the wsgi server so that
            # it can be updated with the new root
            cls.setup_server()
            cls.start()
    setup_class = classmethod(setup_class)

    def teardown_class(cls):
        """Stop the per-class HTTP server."""
        if hasattr(cls, 'setup_server'):
            cls.stop()
    teardown_class = classmethod(teardown_class)

    trap_kbint = False

    def start(cls):
        """Load and start the HTTP server."""
        def trap():
            try:
                cls.httpserver.safe_start()
            except KeyboardInterrupt:
                if not cls.trap_kbint:
                    raise
        threading.Thread(target=trap).start()
        for trial in range(cls.httpserver_startup_timeout):
            if cls.httpserver.ready:
                return
            time.sleep(1)
        raise AssertionError(
            "The HTTP server did not start in the allotted time.")
    start = classmethod(start)

    def stop(cls):
        """Stop the per-class HTTP server."""
        cls.httpserver.stop()
        td = getattr(cls, 'teardown', None)
        if td:
            td()
    stop = classmethod(stop)

    def base(self):
        if (
                (self.httpserver.ssl_adapter is None and self.PORT == 80) or
                (self.httpserver.ssl_adapter is not None and self.PORT == 443)
        ):
            port = ""
        else:
            port = ":%s" % self.PORT

        return "%s://%s%s%s" % (self.scheme, self.HOST, port,
                                self.script_name.rstrip("/"))

    def exit(self):
        sys.exit()

    def getPage(self, url, headers=None, method="GET", body=None,
                protocol=None):
        """Open the url. Return status, headers, body."""
        return webtest.WebCase.getPage(
            self, url, headers, method, body, protocol)

    def skip(self, msg='skipped '):
        raise nose.SkipTest(msg)

    date_tolerance = 2

    def assertEqualDates(self, dt1, dt2, seconds=None):
        """Assert abs(dt1 - dt2) is within Y seconds."""
        if seconds is None:
            seconds = self.date_tolerance

        if dt1 > dt2:
            diff = dt1 - dt2
        else:
            diff = dt2 - dt1
        if not diff < datetime.timedelta(seconds=seconds):
            raise AssertionError('%r and %r are not within %r seconds.' %
                                 (dt1, dt2, seconds))

    def assertInLog(self, msg):
        for m, level, tb in self.log:
            if msg in m or msg in tb:
                return
        raise AssertionError(
            "Log does not contain expected message %s." % repr(msg))


class Request(object):

    def __init__(self, environ):
        self.environ = environ


class Response(object):

    def __init__(self):
        self.status = '200 OK'
        # Note these are the native string type, just like WSGI
        self.headers = {'Content-Type': 'text/html'}
        self.body = None

    def output(self):
        if self.body is None:
            return []
        elif isinstance(self.body, (tuple, list)):
            return [ntob(x) for x in self.body]
        elif isinstance(self.body, basestring):
            return [ntob(self.body)]
        else:
            return self.body


class Controller(object):

    def __call__(self, environ, start_response):
        try:
            req, resp = Request(environ), Response()
            try:
                handler = getattr(
                    self, environ["PATH_INFO"].lstrip("/").replace("/", "_"))
            except AttributeError:
                resp.status = '404 Not Found'
            else:
                output = handler(req, resp)
                if output is not None:
                    resp.body = output
                    if isinstance(output, basestring):
                        cl = len(output)
                    elif isinstance(output, (tuple, list)):
                        cl = sum([len(a) for a in output])
                    else:
                        cl = None
                    if cl is not None:
                        resp.headers.setdefault('Content-Length', str(cl))
            h = []
            for k, v in resp.headers.items():
                if isinstance(v, (tuple, list)):
                    for atom in v:
                        h.append((k, atom))
                else:
                    h.append((k, v))
            start_response(resp.status, h)
            return resp.output()
        except:
            status = "500 Server Error"
            response_headers = [("Content-Type", "text/plain")]
            start_response(status, response_headers, sys.exc_info())
            return format_exc()


class UnixSocketHTTPConnection(HTTPConnection):

    def __init__(self, path=None):
        self.path = path
        HTTPConnection.__init__(self, host="localhost", port=80)

    def connect(self):
        """Connect to the host and port specified in __init__."""
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect(self.path)


def get_default_ssl_adapter():
    """Return an instance of a cheroot.ssllib.SSLAdapter."""
    # Use the default ('pyopenssl' for Python 2 and 'builtin' for 3):
    ssl_adapter_class = ssllib.get_ssl_adapter_class()
    serverpem = os.path.join(thisdir, 'test.pem')
    return ssl_adapter_class(certificate=serverpem, private_key=serverpem)
