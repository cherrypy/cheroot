import collections.abc as _c
import typing as _t

from . import Adapter

class BuiltinSSLAdapter(Adapter):
    CERT_KEY_TO_ENV: _t.Any
    CERT_KEY_TO_LDAP_CODE: _t.Any
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
    @property
    def context(self): ...
    @context.setter
    def context(self, context) -> None: ...
    def wrap(self, sock): ...
    def get_environ(self, sock): ...
    def makefile(self, sock, mode: str = ..., bufsize: int = ...): ...
