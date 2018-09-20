import os
import pytest
import requests
import ssl
from cheroot.ssl.builtin import BuiltinSSLAdapter

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

@pytest.mark.parametrize('SSLAdapter', [ssl.CERT_REQUIRED, ssl.CERT_OPTIONAL, ssl.CERT_NONE], indirect=True)
@pytest.mark.parametrize('client_cert_file', ['client', 'client_ip', 'client_wildcard', 'client_wrong_host', 'client_wrong_ca', None], indirect=True)
def test_cheroot_wsgi_https(SSLAdapter, client_cert_file, make_session_for_cheroot):
    allowed = True

    if client_cert_file is not None:
        assert os.path.exists(client_cert_file)

    if SSLAdapter.context.verify_mode == ssl.CERT_OPTIONAL:
        if client_cert_file is not None and "client_wrong_ca" in client_cert_file:
            allowed = False
    if SSLAdapter.context.verify_mode == ssl.CERT_REQUIRED:
        if client_cert_file is None or "client_wrong_ca" in client_cert_file:
            allowed = False

    my_session = make_session_for_cheroot(
        prefix="https://", ssl_adapter=SSLAdapter, test_app_client="requests", client_cert=client_cert_file,
        client_key=ssl_file("client.key"))

    # The pyriform requests adaptor eats the request verify and cert args as it isn't trivial to pass
    # such args to an instant of WebTest.TestApp.
    # Therefore, although the verify and cert args are set here, they are effectively ignored.
    resp = my_session.get('https://localhost/', verify=SSLAdapter.certificate_chain,
        cert=(client_cert_file, ssl_file("client.key")))
    if allowed is True:
        assert resp.status_code == 200
    else:
        assert resp.status_code == 502
