import collections.abc as _c
import typing as _t

from OpenSSL import SSL

from ..makefile import StreamReader, StreamWriter
from . import Adapter

ssl_conn_type: _t.Type[SSL.Connection]

class SSLFileobjectMixin:
    ssl_timeout: int
    ssl_retry: float
    def recv(self, size): ...
    def readline(self, size: int = ...): ...
    def sendall(self, *args, **kwargs): ...
    def send(self, *args, **kwargs): ...

class SSLFileobjectStreamReader(SSLFileobjectMixin, StreamReader): ...  # type:ignore[misc]
class SSLFileobjectStreamWriter(SSLFileobjectMixin, StreamWriter): ...  # type:ignore[misc]

class SSLConnectionProxyMeta:
    def __new__(mcl, name, bases, nmspc): ...

class SSLConnection:
    def __init__(self, *args) -> None: ...

class pyOpenSSLAdapter(Adapter):
    def __init__(
        self,
        certificate,
        private_key,
        certificate_chain: _t.Any | None = ...,
        ciphers: _t.Any | None = ...,
        *,
        private_key_password: _c.Callable[[], bytes | str]
        | bytes
        | str
        | None = ...,
    ) -> None: ...
    def wrap(self, sock): ...
    def _password_callback(
        self,
        password_max_length: int,
        verify_twice: bool,
        password_or_callback: _c.Callable[[], bytes | str]
        | bytes
        | str
        | None,
        /,
    ) -> bytes: ...
    def get_environ(self): ...
    def makefile(self, sock, mode: str = ..., bufsize: int = ...): ...
    def get_context(self) -> SSL.Context: ...
