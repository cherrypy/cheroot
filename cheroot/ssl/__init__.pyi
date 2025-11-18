from abc import ABC, abstractmethod
from typing import Any

DN_SEPARATOR: str
UTF8_ENCODING: str

def parse_pyopenssl_cert_to_environ(
    cert: Any,
    key_prefix: str,
) -> dict[str, Any]: ...
def parse_x509_cert_to_environ(
    cert: Any,
    key_prefix: str,
) -> dict[str, Any]: ...

class SSLEnvironMixin:
    def _get_core_tls_environ(
        self,
        conn: Any,
    ) -> dict[str, Any]: ...
    def _get_server_cert_environ(self) -> dict[str, Any]: ...
    def _get_client_cert_environ(
        self,
        conn: Any,
        ssl_environ: dict[str, Any],
    ) -> dict[str, Any]: ...

class Adapter(ABC):
    certificate: Any
    private_key: Any
    certificate_chain: Any
    ciphers: Any
    private_key_password: str | bytes | None
    context: Any
    @abstractmethod
    def __init__(
        self,
        certificate,
        private_key,
        certificate_chain: Any | None = ...,
        ciphers: Any | None = ...,
        *,
        private_key_password: str | bytes | None = ...,
    ): ...
    @abstractmethod
    def bind(self, sock): ...
    @abstractmethod
    def wrap(self, sock): ...
    @abstractmethod
    def get_environ(self, conn) -> dict[str, Any]: ...
