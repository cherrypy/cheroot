import pytest
import pyriform
import requests
from webtest import TestApp
import threading
import time
import cheroot.wsgi
import six
import sys
import ssl
from cheroot.ssl.builtin import BuiltinSSLAdapter

import urllib3
urllib3.disable_warnings()

ssl_adapter = BuiltinSSLAdapter(
    certificate='cheroot/test/ssl/server.cert',
    private_key='cheroot/test/ssl/server.key',
    certificate_chain='cheroot/test/ssl/ca.cert'
)
ssl_adapter.context.verify_mode = ssl.CERT_NONE

config = {
    'bind_addr': ('127.0.0.1', 54583),
#    'server': 'wsgi',
    'wsgi_app': None,
}

config['bind_addr'] = '127.0.0.1', 0


class Request:
    """HTTP request container."""

    def __init__(self, environ):
        """Initialize HTTP request."""
        self.environ = environ


class Response:
    """HTTP response container."""

    def __init__(self):
        """Initialize HTTP response."""
        self.status = '200 OK'
        self.headers = {'Content-Type': 'text/html'}
        self.body = None

    def output(self):
        """Generate iterable response body object."""
        if self.body is None:
            return []
        elif isinstance(self.body, six.text_type):
            return [self.body.encode('iso-8859-1')]
        elif isinstance(self.body, six.binary_type):
            return [self.body]
        else:
            return [x.encode('iso-8859-1') for x in self.body]





class Controller:
    """WSGI app for tests."""

    def __call__(self, environ, start_response):
        """WSGI request handler."""
        req, resp = Request(environ), Response()
        try:
            # Python 3 supports unicode attribute names
            # Python 2 encodes them
            handler = self.handlers[environ['PATH_INFO']]
        except KeyError:
            resp.status = '404 Not Found'
        else:
            output = handler(req, resp)
            if (output is not None and
                    not any(resp.status.startswith(status_code)
                            for status_code in ('204', '304'))):
                resp.body = output
                try:
                    resp.headers.setdefault('Content-Length', str(len(output)))
                except TypeError:
                    if not isinstance(output, types.GeneratorType):
                        raise
        start_response(resp.status, resp.headers.items())
        return resp.output()


"""Set up the test server."""
class Root(Controller):

    def hello(req, resp):
        return 'Hello world!'

    handlers = {'/hello': hello}

config['wsgi_app'] = Root()
httpserver = cheroot.wsgi.Server(**config)
httpserver.ssl_adapter = ssl_adapter

threading.Thread(target=httpserver.safe_start).start()
while not httpserver.ready:
    time.sleep(0.1)

print ("bind addr: {}".format(httpserver.bind_addr))

# instruct TestApp to use WSGIProxy with the requests client
my_test_app = TestApp("https://{}:{}#requests".format(*httpserver.bind_addr))

my_test_app.get("https://127.0.0.1:{}/hello".format(httpserver.bind_addr[1]))

adapter = pyriform.WSGIAdapter(my_test_app)
session = requests.Session()
session.mount('https://dummy/', adapter)
resp = session.get('https://dummy/hello')
print (resp.text)


def my_crazy_app(environ, start_response):
    status = '200 OK'
    response_headers = [('Content-type', 'text/plain')]
    start_response(status, response_headers)
    return [b'Hello world!']


addr = '0.0.0.0', 0
httpserver2 = cheroot.wsgi.Server(addr, my_crazy_app)

threading.Thread(target=httpserver2.safe_start).start()
while not httpserver2.ready:
    time.sleep(0.1)

print ("after starting second server, port number is {}".format(httpserver2.bind_addr))

my_test_app = TestApp("http://127.0.0.1:{}".format(httpserver2.bind_addr[1]))
adapter = pyriform.WSGIAdapter(my_test_app)

my_test_app.get("http://127.0.0.1:{}/".format(httpserver2.bind_addr[1]))

session = requests.Session()
session.mount('http://dummy2/', adapter)
resp = session.get('http://dummy2/')
print (resp.text)




