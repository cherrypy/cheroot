import collections.abc as _c
import io
import threading
import typing as _t

from OpenSSL import SSL

from . import Adapter

ssl_conn_type: _t.Type[SSL.Connection]

class SSLFileobjectMixin:
    ssl_timeout: float
    ssl_retry: float
    def recv(self, size): ...
    def readline(self, size: int | None = ...): ...
    def sendall(self, *args, **kwargs): ...
    def send(self, *args, **kwargs): ...

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
    def get_context(self) -> SSL.Context: ...
    def makefile(self, sock, mode: str = ..., bufsize: int = ...): ...

class TLSSocket(SSLFileobjectMixin, io.RawIOBase):
    _ssl_conn: _t.Any
    _sock: _t.Any
    _lock: threading.RLock
    ssl_timeout: float
    ssl_retry: float

    def __init__(
        self,
        ssl_conn: _t.Any,
        ssl_timeout: float | None = None,
        ssl_retry: float | None = 0.01,
    ) -> None: ...
    def recv_into(
        self,
        buffer: bytes,
        nbytes: float | None = None,
    ) -> int: ...
    def send(self, data: bytes) -> int: ...
    def fileno(self) -> int: ...
    def _decref_socketios(self) -> _t.Any: ...
    def shutdown(self, how: int) -> None: ...
    def close(self) -> None: ...
