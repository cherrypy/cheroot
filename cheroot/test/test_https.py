"""HTTPS Tests."""
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

import os
import pytest
import ssl

from cheroot.ssl.builtin import BuiltinSSLAdapter
from cheroot.test import helper
import cheroot
import ddt


def create_wsgi_server(**conf):
    """Create test server."""
    ssl_adapter = BuiltinSSLAdapter(
        certificate=conf.pop('certificate'),
        private_key=conf.pop('private_key'),
        certificate_chain=conf.pop('certificate_chain'))
    ssl_adapter.context.verify_mode = conf.pop('verify_mode', ssl.CERT_NONE)
    server = cheroot.wsgi.Server(**conf)
    server.ssl_adapter = ssl_adapter
    return server


def ssl_file(filename):
    """Return path to given ssl file."""
    return os.path.join('cheroot/test/ssl/', filename)


class HTTPSTestBase(object):
    """Base class for HTTPS tests."""

    available_servers = {'wsgi': create_wsgi_server}
    config = {
        'certificate': 'cheroot/test/ssl/server.cert',
        'private_key': 'cheroot/test/ssl/server.key',
        'certificate_chain': 'cheroot/test/ssl/ca.cert',
    }
    script_name = '/hello'
    ssl_context = None

    @classmethod
    def setup_server(cls):
        """Set up the test server."""
        class Root(helper.Controller):

            def hello(req, resp):
                return 'Hello world!'

            handlers = {'/hello': hello}

        cls.httpserver.wsgi_app = Root()

    def setUp(self):
        """Set up."""
        super(HTTPSTestBase, self).setUp()
        self.ssl_context = ssl.create_default_context(
            cafile='cheroot/test/ssl/ca.cert')
        self.ssl_context.check_hostname = False

    def getPage(self, *args, **kw):
        """Fetch the page."""
        return super(HTTPSTestBase, self).getPage(
            self.script_name, *args,
            raise_subcls=ssl.SSLError, **kw)

    def set_client_cert(self, name):
        """Set client cert."""
        self.ssl_context.load_cert_chain(ssl_file(name + '.cert'),
                                         keyfile=ssl_file('client.key'))

    def assert_allowed(self, client_cert):
        """Assert test page can be fetched when given client cert is used."""
        self.set_client_cert(client_cert)
        self.getPage()
        self.assertStatus('200 OK')

    def assert_reject(self, client_cert):
        """Assert test page cannot be fetched.

        And an SSLError is raised when the given client cert is used.
        """
        self.set_client_cert(client_cert)
        with pytest.raises(ssl.SSLError) as context:
            self.getPage()
        return context


@ddt.ddt
class ClientCertRequiredTests(HTTPSTestBase, helper.CherootWebCase):
    """Test expected outcomes when client cert is required."""

    @classmethod
    def setup_class(cls):
        """Set up for tests."""
        cls.config.update({'verify_mode': ssl.CERT_REQUIRED})
        super(ClientCertRequiredTests, cls).setup_class()

    @ddt.data('client', 'client_ip', 'client_wildcard', 'client_wrong_host')
    def test_allow(self, client_cert):
        """Test that the given client cert is allowed to connect."""
        self.assert_allowed(client_cert)

    def test_reject_wrong_ca(self):
        """Test that the given client cert is not allowed to connect."""
        context = self.assert_reject('client_wrong_ca')
        assert 'tlsv1 alert unknown ca' in str(context.value)


@ddt.ddt
class ClientCertOptionalTests(HTTPSTestBase, helper.CherootWebCase):
    """Test expected outcomes when client cert is optional."""

    @classmethod
    def setup_class(cls):
        """Set up for tests."""
        cls.config.update({'verify_mode': ssl.CERT_OPTIONAL})
        super(ClientCertOptionalTests, cls).setup_class()

    @ddt.data('client', 'client_ip', 'client_wildcard', 'client_wrong_host')
    def test_allow(self, client_cert):
        """Test that the given client cert is allowed to connect."""
        self.assert_allowed(client_cert)

    def test_reject_wrong_ca(self):
        """Test that the given client cert is not allowed to connect."""
        context = self.assert_reject('client_wrong_ca')
        assert 'tlsv1 alert unknown ca' in str(context.value)


@ddt.ddt
class ClientCertIgnoredTests(HTTPSTestBase, helper.CherootWebCase):
    """Test expected outcomes when client cert is ignored."""

    @classmethod
    def setup_class(cls):
        """Set up for tests."""
        cls.config.update({'verify_mode': ssl.CERT_NONE})
        super(ClientCertIgnoredTests, cls).setup_class()

    @ddt.data('client', 'client_ip', 'client_wildcard', 'client_wrong_host',
              'client_wrong_ca')
    def test_allow(self, client_cert):
        """Test that the given client cert is allowed to connect."""
        self.assert_allowed(client_cert)
