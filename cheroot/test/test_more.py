import os
import itertools
import collections
import pytest
import six
import ssl
import trustme
from cheroot.ssl.builtin import BuiltinSSLAdapter

@pytest.fixture(scope='module')
def SSLAdapter(root_CA, tmpdir_factory):
    server_cert = root_CA.issue_server_cert(u"localhost", u"127.0.0.1", u"::1")

    server_dir = tmpdir_factory.mktemp("server")
    server_cert_file = server_dir.join("server.cert")
    server_cert_file.write(server_cert.cert_chain_pems[0].bytes())
    server_pkey_file = server_dir.join("server_pkey")
    server_pkey_file.write(server_cert.private_key_pem.bytes())
    cert_chain_file = server_dir.join("ca.cert")
    cert_chain_file.write(root_CA.cert_pem.bytes())

    ssl_adapter = BuiltinSSLAdapter(
        certificate=str(server_cert_file),
        private_key=str(server_pkey_file),
        certificate_chain=str(cert_chain_file),
    )
    ssl_adapter.context.verify_mode = ssl.CERT_REQUIRED
    return ssl_adapter


@pytest.fixture
def client_cert_files(request, root_CA, tmpdir):
    """Return path to the parametrized client cert or None if None"""
    CertKeyPair = collections.namedtuple('CertKeyPair', 'cert,pkey,type')
    if request.param is None:
        return CertKeyPair(None, None, None)

    cert_type = request.param
    cert_type_to_args = {
        "client":            [u"localhost", u"127.0.0.1", u"::1"],
        # as far as I know, testme doesn't respect only ips for local host
        "client_ip":         [u"127.0.0.1", u"::1"],
        "client_wildcard":   [u"*.localhost"],
        "client_wrong_host": [u"cherrypy.org", u"github.com"],
    }

    client_cert = None
    if cert_type == "client_wrong_ca":
        another_CA = trustme.CA()
        client_cert = \
            another_CA.issue_server_cert(*cert_type_to_args["client"])
    elif cert_type in cert_type_to_args:
        client_cert = root_CA.issue_server_cert(*cert_type_to_args[cert_type])

    client_dir = tmpdir.mkdir("client")

    client_cert_file = client_dir.join("client.cert")
    client_cert_file.write(client_cert.cert_chain_pems[0].bytes())
    client_pkey_file = client_dir.join("server_pkey")
    client_pkey_file.write(client_cert.private_key_pem.bytes())
    return CertKeyPair(str(client_cert_file), str(client_pkey_file), cert_type)


class TestClientCertValidation:

    @pytest.fixture(autouse=True)
    def setup(self, SSLAdapter):
        verify_save = SSLAdapter.context.verify_mode
        SSLAdapter.context.verify_mode = self.server_verify_mode
        self._SSLAdapter = SSLAdapter
        print ("before yield, verify mode is ", self.server_verify_mode)
        yield SSLAdapter
        print ("after yield")
        SSLAdapter.context.verify_mode = verify_save

    def make_wsgi_https_request(
            self, SSLAdapter, client_cert_files, make_session_for_cheroot):
        my_session = make_session_for_cheroot(
            "localhost", prefix="https://", ssl_adapter=SSLAdapter,
            test_app_client="requests", client_cert=client_cert_files.cert,
            client_key=client_cert_files.pkey)

        # The pyriform requests adaptor eats the request verify and cert args
        # as it isn't trivial to pass such args to an instant of
        # WebTest.TestApp.  Therefore, although the verify and cert args are
        # set here, they are effectively ignored.
        resp = my_session.get('https://localhost/',
            verify=SSLAdapter.certificate_chain,
            cert=(client_cert_files.cert, client_cert_files.pkey))
        return resp


class TestCertRequired(TestClientCertValidation):
    server_verify_mode = ssl.CERT_REQUIRED

    @pytest.mark.parametrize('client_cert_files',
        ['client', 'client_ip', 'client_wildcard', 'client_wrong_host'],
        indirect=True)
    def test_valid_certs(self, client_cert_files, make_session_for_cheroot):

        resp = self.make_wsgi_https_request(
            self._SSLAdapter, client_cert_files, make_session_for_cheroot)
        assert resp.status_code == 200

    @pytest.mark.parametrize('client_cert_files', ['client_wrong_ca', None],
                             indirect=True)
    def test_invalid_certs(self, client_cert_files, make_session_for_cheroot):
        resp = self.make_wsgi_https_request(
            self._SSLAdapter, client_cert_files, make_session_for_cheroot)
        assert resp.status_code == 502


class TestCertOptional(TestClientCertValidation):
    server_verify_mode = ssl.CERT_OPTIONAL

    @pytest.mark.parametrize('client_cert_files',
        ['client', 'client_ip', 'client_wildcard', 'client_wrong_host', None],
        indirect=True)
    def test_valid_certs(self, client_cert_files, make_session_for_cheroot):
        resp = self.make_wsgi_https_request(
            self._SSLAdapter, client_cert_files, make_session_for_cheroot)
        assert resp.status_code == 200

    @pytest.mark.parametrize('client_cert_files', ['client_wrong_ca'],
        indirect=True)
    def test_invalid_certs(self, client_cert_files, make_session_for_cheroot):
        resp = self.make_wsgi_https_request(
            self._SSLAdapter, client_cert_files, make_session_for_cheroot)
        assert resp.status_code == 502


class TestCertNone(TestClientCertValidation):
    server_verify_mode = ssl.CERT_NONE

    @pytest.mark.parametrize('client_cert_files',
        ['client', 'client_ip', 'client_wildcard', 'client_wrong_host',
        'client_wrong_ca', None], indirect=True)
    def test_valid_certs(self, client_cert_files, make_session_for_cheroot):
        resp = self.make_wsgi_https_request(
            self._SSLAdapter, client_cert_files, make_session_for_cheroot)
        assert resp.status_code == 200

