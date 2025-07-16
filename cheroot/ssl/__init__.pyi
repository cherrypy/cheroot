from abc import ABC, abstractmethod
from typing import Any

class Adapter(ABC):
    certificate: Any
    private_key: Any
    certificate_chain: Any
    ciphers: Any
    private_key_password: Any
    context: Any
    @abstractmethod
    def __init__(
        self,
        certificate,
        private_key,
        certificate_chain: Any | None = ...,
        ciphers: Any | None = ...,
        private_key_password: Any | None = ...,
    ): ...
    @abstractmethod
    def bind(self, sock): ...
    @abstractmethod
    def wrap(self, sock): ...
    @abstractmethod
    def get_environ(self): ...
    @abstractmethod
    def makefile(self, sock, mode: str = ..., bufsize: int = ...): ...
