from cheroot import makefile


__metaclass__ = type


class MockSocket:
    def __init__(self):
        self.messages = []

    def recv_into(self, buf):
        if not self.messages:
            return 0
        msg = self.messages.pop(0)
        for index, byte in enumerate(msg):
            buf[index] = byte
        return len(msg)

    def recv(self, size):
        try:
            return self.messages.pop(0)
        except IndexError:
            return ''

    def send(self, val):
        return len(val)


def test_bytes_read():
    sock = MockSocket()
    sock.messages.append(b'foo')
    rfile = makefile.MakeFile(sock, 'r')
    rfile.read()
    assert rfile.bytes_read == 3


def test_bytes_written():
    sock = MockSocket()
    sock.messages.append(b'foo')
    wfile = makefile.MakeFile(sock, 'w')
    wfile.write(b'bar')
    assert wfile.bytes_written == 3
