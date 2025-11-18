from typing import Any, Type

from OpenSSL import SSL

from ..makefile import StreamReader, StreamWriter
from . import Adapter

ssl_conn_type: Type[SSL.Connection]

class SSLFileobjectStreamReader(StreamReader): ...  # type:ignore[misc]
class SSLFileobjectStreamWriter(StreamWriter): ...  # type:ignore[misc]

class pyOpenSSLAdapter(Adapter):
    def __init__(
        self,
        certificate,
        private_key,
        certificate_chain: Any | None = ...,
        ciphers: Any | None = ...,
        *,
        private_key_password: str | bytes | None = ...,
    ) -> None: ...
    def bind(self, sock): ...
    def wrap(self, sock): ...
    def _password_callback(
        self,
        password_max_length: int,
        _verify_twice: bool,
        password: bytes | str | None,
        /,
    ) -> bytes: ...
    def get_environ(self, conn) -> dict: ...
    def get_context(self) -> SSL.Context: ...
