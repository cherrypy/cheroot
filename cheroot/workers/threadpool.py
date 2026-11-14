"""A thread-based worker pool.

.. spelling::

   joinable
"""

import logging
import queue
import socket
import threading
import time
import warnings

from jaraco.functools import pass_none


__all__ = ('ThreadPool', 'WorkerThread')


class TrueyZero:
    """Object which equals and does math like the integer 0 but evals True."""

    def __add__(self, other):
        return other

    def __radd__(self, other):
        return other


trueyzero = TrueyZero()

_SHUTDOWNREQUEST = object()


class _ShrinkRequest:
    """A request that shrink() queued for one thread to shut down."""

    taken = False
    """Whether a worker took it, so that its shutdown is no longer due."""

    cancelled = False
    """Whether its shrink() call gave its shutdown back before then."""

    def __init__(self, run):
        """Initialize a request of one run of the pool."""
        self.run = run


class _RequestQueue(queue.Queue):
    """A queue of connections, and of requests for workers to shut down."""

    def put_shutdown(self, request):
        """Queue a shutdown request, even when the queue has no room."""
        # stop() then always reaches its timeout, which closes the
        # connection that a worker may be stuck on
        with self.not_empty:
            self._put(request)
            self.unfinished_tasks += 1
            self.not_empty.notify()


class WorkerThread(threading.Thread):
    """Thread which continuously polls a Queue for Connection objects.

    Due to the timing issues of polling a Queue, a WorkerThread does not
    check its own 'ready' flag after it has started. To stop the thread,
    it is necessary to stick a _SHUTDOWNREQUEST object onto the Queue
    (one for each running WorkerThread).
    """

    conn = None
    """The current connection pulled off the Queue, or None."""

    server = None
    """The HTTP Server which spawned this thread, and which owns the
    Queue and is placing active connections into it."""

    ready = False
    """A simple flag for the calling server to know when this thread
    has begun polling the Queue."""

    _retiring = False
    """Whether this thread took a shutdown request, and is exiting."""

    _run = None
    """The run of the pool that started this thread, if one did."""

    def __init__(self, server):
        """Initialize WorkerThread instance.

        Args:
            server (cheroot.server.HTTPServer): web server object
                receiving this request
        """
        self.ready = False
        self.server = server

        self.requests_seen = 0
        self.bytes_read = 0
        self.bytes_written = 0
        self.start_time = None
        self.work_time = 0
        self.stats = {
            'Requests': lambda s: (
                self.requests_seen
                + (
                    (self.start_time is None and trueyzero)
                    or self.conn.requests_seen
                )
            ),
            'Bytes Read': lambda s: (
                self.bytes_read
                + (
                    (self.start_time is None and trueyzero)
                    or self.conn.rfile.bytes_read
                )
            ),
            'Bytes Written': lambda s: (
                self.bytes_written
                + (
                    (self.start_time is None and trueyzero)
                    or self.conn.wfile.bytes_written
                )
            ),
            'Work Time': lambda s: (
                self.work_time
                + (
                    (self.start_time is None and trueyzero)
                    or time.time() - self.start_time
                )
            ),
            'Read Throughput': lambda s: (
                s['Bytes Read'](s) / (s['Work Time'](s) or 1e-6)
            ),
            'Write Throughput': lambda s: (
                s['Bytes Written'](s) / (s['Work Time'](s) or 1e-6)
            ),
        }
        threading.Thread.__init__(self)

    def run(self):
        """Set up incoming HTTP connection processing loop.

        This is the thread's entry-point. It performs lop-layer
        exception handling and interrupt processing.
        :exc:`KeyboardInterrupt` and :exc:`SystemExit` bubbling up
        from the inner-layer code constitute a global server interrupt
        request. When they happen, the worker thread exits.

        :raises BaseException: when an unexpected non-interrupt
                               exception leaks from the inner layers

        # noqa: DAR401 KeyboardInterrupt SystemExit
        """
        self.server.stats['Worker Threads'][self.name] = self.stats
        self.ready = True
        try:
            self._process_connections_until_interrupted()
        except (KeyboardInterrupt, SystemExit) as interrupt_exc:
            interrupt_cause = interrupt_exc.__cause__ or interrupt_exc
            self.server.error_log(
                f'Setting the server interrupt flag to {interrupt_cause!r}',
                level=logging.DEBUG,
            )
            self.server.interrupt = interrupt_cause
        except BaseException as underlying_exc:
            # NOTE: This is the last resort logging with the last dying breath
            # NOTE: of the worker. It is only reachable when exceptions happen
            # NOTE: in the `finally` branch of the internal try/except block.
            self.server.error_log(
                'A fatal exception happened. Setting the server interrupt flag'
                f' to {underlying_exc!r} and giving up.'
                '\N{NEW LINE}\N{NEW LINE}'
                'Please, report this on the Cheroot tracker at '
                '<https://github.com/cherrypy/cheroot/issues/new/choose>, '
                'providing a full reproducer with as much context and details as possible.',
                level=logging.CRITICAL,
                traceback=True,
            )
            self.server.interrupt = underlying_exc
            raise
        finally:
            self.ready = False

    def _get_request(self):
        """Get a connection, or a shutdown request if this thread exits."""
        while True:
            conn = self.server.requests.get()
            if conn is _SHUTDOWNREQUEST:
                if self._run is None or self.server.requests._stops(self):
                    return conn
            elif not isinstance(conn, _ShrinkRequest):
                return conn
            elif self.server.requests._retires(self, conn):
                return _SHUTDOWNREQUEST

    def _process_connections_until_interrupted(self):
        """Process incoming HTTP connections in an infinite loop.

        Retrieves incoming connections from thread pool, processing
        them one by one.

        :raises SystemExit: on the internal requests to stop the
                            server instance
        """
        while True:
            conn = self._get_request()
            if conn is _SHUTDOWNREQUEST:
                return

            self.conn = conn
            is_stats_enabled = self.server.stats['Enabled']
            if is_stats_enabled:
                self.start_time = time.time()
            keep_conn_open = False
            try:  # noqa: WPS243 check "Found too long `finally` block: 3 > 2"
                keep_conn_open = conn.communicate()
            except ConnectionError as connection_error:
                keep_conn_open = False  # Drop the connection cleanly
                self.server.error_log(
                    'Got a connection error while handling a '
                    f'connection from {conn.remote_addr!s}:'
                    f'{conn.remote_port!s} ({connection_error!s})',
                    level=logging.INFO,
                )
                continue
            except (KeyboardInterrupt, SystemExit) as shutdown_request:
                # Shutdown request
                keep_conn_open = False  # Drop the connection cleanly
                self.server.error_log(
                    'Got a server shutdown request while handling a '
                    f'connection from {conn.remote_addr!s}:'
                    f'{conn.remote_port!s} ({shutdown_request!s})',
                    level=logging.DEBUG,
                )
                raise SystemExit(
                    str(shutdown_request),
                ) from shutdown_request
            except BaseException as unhandled_error:
                # NOTE: Only a shutdown request should bubble up to the
                # NOTE: external cleanup code. Otherwise, this thread dies.
                # NOTE: If this were to happen, the threadpool would still
                # NOTE: list a dead thread without knowing its state. And
                # NOTE: the calling code would fail to schedule processing
                # NOTE: of new requests.
                self.server.error_log(
                    'Unhandled error while processing an incoming '
                    f'connection {unhandled_error!r}',
                    level=logging.ERROR,
                    traceback=True,
                )
                continue  # Prevent the thread from dying
            finally:
                # NOTE: Any exceptions coming from within `finally` may
                # NOTE: kill the thread, causing the threadpool to only
                # NOTE: contain references to dead threads rendering the
                # NOTE: server defunct, effectively meaning a DoS.
                # NOTE: Ideally, things called here should process
                # NOTE: everything recoverable internally. Any unhandled
                # NOTE: errors will bubble up into the outer try/except
                # NOTE: block. They will be treated as fatal and turned
                # NOTE: into server shutdown requests and then reraised
                # NOTE: unconditionally.
                if keep_conn_open:
                    self.server.put_conn(conn)
                else:
                    conn.close()
                if is_stats_enabled:
                    self.requests_seen += conn.requests_seen
                    self.bytes_read += conn.rfile.bytes_read
                    self.bytes_written += conn.wfile.bytes_written
                    self.work_time += time.time() - self.start_time
                    self.start_time = None
                self.conn = None


class ThreadPool:
    """A Request Queue for an HTTPServer which pools threads.

    ThreadPool objects must provide min, get(), put(obj), start()
    and stop(timeout) attributes.
    """

    def __init__(  # pylint: disable=too-many-positional-arguments
        self,
        server,
        min=10,
        max=-1,
        accepted_queue_size=-1,
        accepted_queue_timeout=10,
    ):
        """Initialize HTTP requests queue instance.

        Args:
            server (cheroot.server.HTTPServer): web server object
                receiving this request
            min (int): minimum number of worker threads
            max (int): maximum number of worker threads (-1/inf for no max)
            accepted_queue_size (int): maximum number of active
                requests in queue
            accepted_queue_timeout (int): timeout for putting request
                into queue

        :raises ValueError: if the min/max values are invalid
        :raises TypeError: if the max is not an integer or inf
        """
        if min < 1:
            raise ValueError(f'min={min!s} must be > 0')

        if max == float('inf'):
            pass
        elif not isinstance(max, int) or max == 0:
            raise TypeError(
                'Expected an integer or the infinity value for the `max` '
                f'argument but got {max!r}.',
            )
        elif max < 0:
            max = float('inf')

        if max < min:
            raise ValueError(
                f'max={max!s} must be > min={min!s} (or infinity for no max)',
            )

        self.server = server
        self.min = min
        self.max = max
        self._threads = []
        self._queue = _RequestQueue(maxsize=accepted_queue_size)
        self._queue_put_timeout = accepted_queue_timeout
        self.get = self._queue.get
        # Guards the number of shutdowns that shrink() asked for and that
        # no thread has taken yet, which threads take them, and the pool's
        # run: stop() ends a run, and the threads of the runs it ended
        # shut down on a stop request
        self._lock = threading.Lock()
        self._shutdowns_due = 0
        self._run = 0

    def start(self):
        """Start the pool of threads.

        :raises RuntimeError: if the pool is already started
        """
        with self._lock:
            if self._threads:
                raise RuntimeError('Threadpools can only be started once.')
            self._grow(self.min)

    @property
    def idle(self):
        """Number of worker threads which are idle. Read-only."""
        # The threads and the shutdowns due change together as a worker
        # takes a shrink request
        with self._lock:
            idles = len([t for t in self._serving() if t.conn is None])
            return max(idles - self._shutdowns_due, 0)

    def put(self, obj):
        """Put request into queue.

        Args:
            obj (:py:class:`~cheroot.server.HTTPConnection`): HTTP connection
                waiting to be processed
        """
        self._queue.put(obj, block=True, timeout=self._queue_put_timeout)

    def _clear_dead_threads(self):
        # Remove any dead threads from our list
        for t in [t for t in self._threads if not t.is_alive()]:
            self._threads.remove(t)

    def _serving(self):
        """Return the threads that run and that are not shutting down."""
        # A thread clears `ready` as it exits. Workers call this, and before
        # Python 3.13, is_alive() can fail when two threads call it, or
        # join(), at once for a thread that is exiting.
        return [
            t
            for t in self._threads
            if t.ready and t._run == self._run and not t._retiring
        ]

    def grow(self, amount):
        """Spawn new worker threads (not above self.max)."""
        with self._lock:
            self._grow(amount)

    def _grow(self, amount):
        budget = max(self.max - len(self._threads), 0)
        n_new = min(amount, budget)

        workers = [self._spawn_worker() for i in range(n_new)]
        for worker in workers:
            while not worker.ready:
                time.sleep(0.1)
        self._threads.extend(workers)

    def _spawn_worker(self):
        worker = WorkerThread(self.server)
        worker.name = f'CP Server {worker.name!s}'
        worker._run = self._run
        worker.start()
        return worker

    def shrink(self, amount):
        """Kill off worker threads (not below self.min).

        Threads that earlier calls asked to shut down count as gone.
        """
        with self._lock:
            # Remove any dead threads from our list
            self._clear_dead_threads()

            # calculate the number of threads above the minimum, without
            # those that earlier calls asked to shut down
            n_removable = max(
                len(self._serving()) - self._shutdowns_due - self.min,
                0,
            )

            # don't remove more than amount
            n_to_remove = min(amount, n_removable)
            # Count them as due before they're queued, so that a concurrent
            # shrink() call sees them and doesn't pick the same threads
            self._shutdowns_due += n_to_remove
            requests = [_ShrinkRequest(self._run) for _ in range(n_to_remove)]

        # put a request on the queue for each shutdown
        n_queued = 0
        try:
            for request in requests:
                self._queue.put(request)
                n_queued += 1
        finally:
            self._cancel(requests[n_queued:])

    def _cancel(self, requests):
        """Give back the shutdowns of requests that no worker has taken."""
        # A put() was interrupted, such as while it waited for room, maybe
        # after its request got into the queue, where a worker skips it now
        with self._lock:
            for request in requests:
                # A stop() since then forgot the shutdowns of its run
                if not request.taken and request.run == self._run:
                    self._shutdowns_due -= 1
                request.cancelled = True

    def _retires(self, worker, request):
        """Tell whether a worker that took a shrink request shuts down."""
        with self._lock:
            # A stop() forgot the shutdowns of the run it ended
            if request.cancelled or request.run != self._run:
                return False
            request.taken = True
            self._shutdowns_due -= 1
            # Another thread may have exited since shrink() was called
            if len(self._serving()) <= self.min:
                return False
            worker._retiring = True
            return True

    def _stops(self, worker):
        """Tell whether a worker that took a stop request shuts down."""
        with self._lock:
            # One that a stop() left behind does not end a later run
            if worker._run == self._run:
                return False
            worker._retiring = True
            return True

    def stop(self, timeout=5):
        """Terminate all worker threads.

        Args:
            timeout (int): time to wait for threads to stop gracefully
        """
        # for compatability, negative timeouts are treated like None
        # TODO: treat negative timeouts like already expired timeouts
        if timeout is not None and timeout < 0:
            timeout = None
            warnings.warning(
                'In the future, negative timeouts to Server.stop() '
                'will be equivalent to a timeout of zero.',
                stacklevel=2,
            )

        if timeout is None:
            endtime = float('inf')
        else:
            endtime = time.time() + timeout

        with self._lock:
            # End the run. The shutdowns that shrink() asked for are no
            # longer due, and every thread that has not taken a request,
            # of this run or of a stop() that was interrupted, needs one.
            self._run += 1
            self._shutdowns_due = 0
            threads = [t for t in self._threads if t.is_alive()]
            n_running = len([t for t in threads if not t._retiring])

        # Must shut down threads here so the code that calls
        # this method can know when all threads are stopped.
        for _ in range(n_running):
            self._queue.put_shutdown(_SHUTDOWNREQUEST)

        ignored_errors = (
            # Raised when start_response called >1 time w/o exc_info or
            # wsgi write is called before start_response. See cheroot#261
            RuntimeError,
            # Ignore repeated Ctrl-C. See cherrypy#691.
            KeyboardInterrupt,
        )

        current_thread = threading.current_thread()
        for worker in threads:
            if worker is current_thread:
                continue
            remaining_time = timeout and endtime - time.time()
            try:
                worker.join(remaining_time)
                if worker.is_alive():
                    # Timeout exhausted; forcibly shut down the socket.
                    self._force_close(worker.conn)
                    worker.join()
            except ignored_errors:
                pass

        with self._lock:
            # A thread still running keeps the pool from starting again,
            # unless it is this one, which exits after its connection
            self._threads[:] = [
                t
                for t in self._threads
                if t.is_alive() and t is not current_thread
            ]

    @staticmethod
    @pass_none
    def _force_close(conn):
        if conn.rfile.closed:
            return
        try:
            try:
                conn.socket.shutdown(socket.SHUT_RD)
            except TypeError:
                # pyOpenSSL sockets don't take an arg
                conn.socket.shutdown()
        except OSError:
            # shutdown sometimes fails (race with 'closed' check?)
            # ref #238
            pass

    @property
    def qsize(self):
        """The queue size."""
        return self._queue.qsize()
