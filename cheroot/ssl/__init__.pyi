import collections.abc as _c
import typing as _t
from abc import ABC, abstractmethod

class Adapter(ABC):
    certificate: _t.Any
    private_key: _t.Any
    certificate_chain: _t.Any
    ciphers: _t.Any
    private_key_password: _c.Callable[[], bytes | str] | bytes | str | None
    context: _t.Any

    @abstractmethod
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
    ): ...
    def bind(self, sock): ...
    @abstractmethod
    def wrap(self, sock): ...
    @abstractmethod
    def get_environ(self): ...
    @abstractmethod
    def makefile(self, sock, mode: str = ..., bufsize: int = ...): ...
    def _prompt_for_tls_password(self) -> str: ...
