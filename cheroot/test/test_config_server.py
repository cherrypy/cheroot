"""Tests for the CherryPy configuration system."""

import os

import pytest

from cheroot.test import helper


pytestmark = pytest.mark.skip(reason='Depends on CherryPy')


localDir = os.path.join(os.getcwd(), os.path.dirname(__file__))


#                             Client-side code                             #


class ServerConfigTests(helper.CherootWebCase):

    @staticmethod
    def setup_server():

        class Root:

            def index(self):
                return cherrypy.request.wsgi_environ['SERVER_PORT']

            @cherrypy.expose
            def upload(self, file):
                return 'Size: %s' % len(file.file.read())

            @cherrypy.expose
            @cherrypy.config(**{'request.body.maxbytes': 100})
            def tinyupload(self):
                return cherrypy.request.body.read()

        cherrypy.tree.mount(Root())

        cherrypy.config.update({
            'server.socket_host': '0.0.0.0',
            'server.socket_port': 9876,
            'server.max_request_body_size': 200,
            'server.max_request_header_size': 500,
            'server.socket_timeout': 0.5,

            # Test explicit server.instance
            'server.2.instance': 'cherrypy._cpwsgi_server.CPWSGIServer',
            'server.2.socket_port': 9877,

            # Test non-numeric <servername>
            # Also test default server.instance = builtin server
            'server.yetanother.socket_port': 9878,
        })

    PORT = 9876

    def testBasicConfig(self):
        self.getPage('/')
        self.assertBody(str(self.PORT))

    def testAdditionalServers(self):
        if self.scheme == 'https':
            return self.skip('not available under ssl')
        self.PORT = 9877
        self.getPage('/')
        self.assertBody(str(self.PORT))
        self.PORT = 9878
        self.getPage('/')
        self.assertBody(str(self.PORT))

    def testMaxRequestSizePerHandler(self):
        if getattr(cherrypy.server, 'using_apache', False):
            return self.skip('skipped due to known Apache differences... ')

        self.getPage('/tinyupload', method='POST',
                     headers=[('Content-Type', 'text/plain'),
                              ('Content-Length', '100')],
                     body='x' * 100)
        self.assertStatus(200)
        self.assertBody('x' * 100)

        self.getPage('/tinyupload', method='POST',
                     headers=[('Content-Type', 'text/plain'),
                              ('Content-Length', '101')],
                     body='x' * 101)
        self.assertStatus(413)

    def testMaxRequestSize(self):
        if getattr(cherrypy.server, 'using_apache', False):
            return self.skip('skipped due to known Apache differences... ')

        for size in (500, 5000, 50000):
            self.getPage('/', headers=[('From', 'x' * 500)])
            self.assertStatus(413)

        # Test for https://github.com/cherrypy/cherrypy/issues/421
        # (Incorrect border condition in readline of SizeCheckWrapper).
        # This hangs in rev 891 and earlier.
        lines256 = 'x' * 248
        self.getPage('/',
                     headers=[('Host', '%s:%s' % (self.HOST, self.PORT)),
                              ('From', lines256)])

        # Test upload
        cd = (
            'Content-Disposition: form-data; '
            'name="file"; '
            'filename="hello.txt"'
        )
        body = '\r\n'.join([
            '--x',
            cd,
            'Content-Type: text/plain',
            '',
            '%s',
            '--x--'])
        partlen = 200 - len(body)
        b = body % ('x' * partlen)
        h = [('Content-type', 'multipart/form-data; boundary=x'),
             ('Content-Length', '%s' % len(b))]
        self.getPage('/upload', h, 'POST', b)
        self.assertBody('Size: %d' % partlen)

        b = body % ('x' * 200)
        h = [('Content-type', 'multipart/form-data; boundary=x'),
             ('Content-Length', '%s' % len(b))]
        self.getPage('/upload', h, 'POST', b)
        self.assertStatus(413)
