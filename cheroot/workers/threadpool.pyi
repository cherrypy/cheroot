import queue
import threading
import typing as _t

__all__ = ('ThreadPool', 'WorkerThread')

class TrueyZero:
    def __add__(self, other): ...
    def __radd__(self, other): ...

trueyzero: TrueyZero

class _RetirementRequest: ...

class _RequestQueue(queue.Queue[_t.Any]):
    def put_shutdown(self, request: object) -> None: ...

class WorkerThread(threading.Thread):
    conn: _t.Any
    server: _t.Any
    ready: bool
    _retiring: bool
    _run: int | None
    requests_seen: int
    bytes_read: int
    bytes_written: int
    start_time: _t.Any
    work_time: int
    stats: _t.Any
    def __init__(self, server): ...
    def run(self) -> None: ...
    def _get_request(self) -> _t.Any: ...

class ThreadPool:
    server: _t.Any
    min: _t.Any
    max: _t.Any
    get: _t.Any
    _lock: threading.Lock
    _retirements_due: set[_RetirementRequest]
    _run: int
    _stop_lock: threading.Lock
    def __init__(
        self,
        server,
        min: int = ...,
        max: int = ...,
        accepted_queue_size: int = ...,
        accepted_queue_timeout: int = ...,
    ) -> None: ...
    def start(self) -> None: ...
    @property
    def idle(self): ...
    def put(self, obj) -> None: ...
    def grow(self, amount) -> None: ...
    def _grow(self, amount) -> None: ...
    def shrink(self, amount) -> None: ...
    def _serving(self) -> list[WorkerThread]: ...
    def _decide_retirement(
        self,
        worker: WorkerThread,
        request: _RetirementRequest,
    ) -> bool: ...
    def _stops(self, worker: WorkerThread) -> bool: ...
    def stop(self, timeout: int = ...) -> None: ...
    def _wait_for(
        self,
        threads: list[WorkerThread],
        timeout: float | None,
        endtime: float,
    ) -> None: ...
    @property
    def qsize(self) -> int: ...
