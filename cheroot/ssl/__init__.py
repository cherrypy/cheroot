class Adapter(object):

    """Base class for SSL driver library adapters.

    Required methods:

        * ``wrap(sock) -> (wrapped socket, ssl environ dict)``
        * ``makefile(sock, mode='r', bufsize=DEFAULT_BUFFER_SIZE) ->
          socket file object``
    """

    def __init__(self, certificate, private_key, certificate_chain=None):
        self.certificate = certificate
        self.private_key = private_key
        self.certificate_chain = certificate_chain

    def wrap(self, sock):
        raise NotImplemented

    def makefile(self, sock, mode='r', bufsize=-1):
        raise NotImplemented
