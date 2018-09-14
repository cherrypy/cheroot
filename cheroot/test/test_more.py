import os
import pytest
import requests
import ssl
from cheroot.ssl.builtin import BuiltinSSLAdapter

class TestMore(object):

    def test_more_wsgi_server_one(self, crazy_wsgi_session):
        resp = crazy_wsgi_session.get('http://crazy_app/')
        print ("inside test_more_wsgi_server_one, response is {}".format(resp))
        assert 1 == 1
        assert 1 == 0

    def test_more_wsgi_server_two(self, crazy_wsgi_https_session):
        resp = crazy_wsgi_https_session.get('https://crazy_app2/')
        print ("inside test_more_wsgi_server_two, response is {}".format(resp))
        assert 1 == 1
        assert 1 == 0

    def test_more_wsgi_server_three(self, make_session_for_cheroot):
        ssl_adapter = BuiltinSSLAdapter(
            certificate='test/ssl/server.cert',
            private_key='test/ssl/server.key',
            certificate_chain='test/ssl/ca.cert'
        )
        ssl_adapter.context.verify_mode = ssl.CERT_NONE
        my_session = make_session_for_cheroot(prefix="https://try_this", ssl_adapter=ssl_adapter)
        resp = my_session.get("https://try_this")
        print("inside test_more_wsgi_server_three, response code is {}".format(resp))
        print("inside test_more_wsgi_server_three, response text is:{}".format(resp.text))
        assert 1 == 1
        assert 1 == 0

def ssl_file(filename):
    """Return path to given ssl file."""
    return os.path.join('test', 'ssl', filename)
    #return os.path.join('cheroot', 'test', 'ssl', filename)

@pytest.fixture
def SSLAdapter(request):
    ssl_adapter = BuiltinSSLAdapter(
        certificate=ssl_file('server.cert'),
        private_key=ssl_file('server.key'),
        certificate_chain=ssl_file('ca.cert'),
    )
    ssl_adapter.context.verify_mode = request.param
    return ssl_adapter

@pytest.fixture
def client_cert_file(request):
    """Return path to the parametrized client cert or None if None"""
    if request.param is None:
        return None
    return ssl_file('{}.cert'.format(request.param))

    #@ddt.data('client', 'client_ip', 'client_wildcard', 'client_wrong_host',
              #'client_wrong_ca')
@pytest.mark.parametrize('SSLAdapter', [ssl.CERT_REQUIRED, ssl.CERT_OPTIONAL, ssl.CERT_NONE], indirect=True)
@pytest.mark.parametrize('client_cert_file', ['client', 'client_ip', 'client_wildcard', 'client_wrong_host', 'client_wrong_ca', None], indirect=True)
def test_https_jeff(SSLAdapter, client_cert_file, make_session_for_cheroot):
    allowed = True

    if client_cert_file is not None:
        assert os.path.exists(client_cert_file)


    if SSLAdapter.context.verify_mode == ssl.CERT_OPTIONAL:
        if client_cert_file is not None and client_cert_file.endswith('client_wrong_ca'):
            allowed = False
    if SSLAdapter.context.verify_mode == ssl.CERT_REQUIRED:
        if client_cert_file is None or client_cert_file.endswith('client_wrong_ca'):
            allowed = False

    my_session = make_session_for_cheroot(prefix="https://", ssl_adapter=SSLAdapter)

    if allowed is True:
        resp = my_session.get('https://localhost/', verify=SSLAdapter.certificate_chain, cert=client_cert_file)
        #print ("response: ", resp.text)
        assert resp.status_code == 200
    else:
        print (dir(SSLAdapter))
        with pytest.raises(ssl.SSLError) as exc_info:
            resp = my_session.get('https://localhost/', verify=SSLAdapter.certificate_chain, cert=client_cert_file)
        # assert 'tlsv1 alert unknown ca' in str(exc_info.value)
        # OR
        # assert ' peer did not return a certificate' in str(exc_info.value)
        assert resp.status_code == 502
        assert 1 == 0





#class TestHttps(object):

