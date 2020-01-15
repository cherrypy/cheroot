"""Monitor for threadpool."""
__metaclass__ = type

import threading
import time

from dynpool import DynamicPoolResizer


class BackgroundTask(threading.Thread):
    """A subclass of threading.Thread whose run() method repeats.

    Use this class for most repeating tasks. It uses time.sleep() to wait
    for each interval, which isn't very responsive; that is, even if you call
    self.cancel(), you'll have to wait until the sleep() call finishes before
    the thread stops. To compensate, it defaults to being daemonic, which means
    it won't delay stopping the whole process.

    :param int interval: time interval between invocation of input function
    :param function: callable that needs to be invoked
    :param args: list of arguments to pass to the function
    :param kwargs: dictionary of keyword args to pass to the function
    """

    def __init__(self, interval, function, name=None, args=None, kwargs=None):
        """Initialize a BackgroundTask."""
        super(BackgroundTask, self).__init__(name=name)
        self.interval = interval
        self.function = function
        self.args = args if args is not None else []
        self.kwargs = kwargs if kwargs is not None else {}
        self.running = False
        self.daemon = True

    def cancel(self):
        """Cancel the task."""
        self.running = False

    def run(self):
        """Invoke the callable with the given interval."""
        self.running = True
        while self.running:
            # Any error in the calling function will be raised immediately
            self.function(*self.args, **self.kwargs)
            time.sleep(self.interval)


class Monitor:
    """Monitor a BackgroundTask."""

    callback = None
    """The function to call at intervals."""

    frequency = 60
    """The time in seconds between callback runs."""

    thread = None
    """A :class:`BackgroundTask` thread."""

    def __init__(self, callback, frequency=60, name=None):
        """Initialize Monitor."""
        self.callback = callback
        self.frequency = frequency
        self.thread = None
        self.name = name or self.__class__.__name__

    def start(self):
        """Start our callback in its own background thread."""
        if self.frequency <= 0:
            raise RuntimeError('The frequency must be a positive number')

        if self.thread is not None:
            raise RuntimeError('Only one background task can be monitored')

        self.thread = BackgroundTask(
            self.frequency,
            self.callback,
            name=self.name,
        )
        self.thread.start()

    def stop(self):
        """Stop our callback's background task thread."""
        if self.thread is None:
            return
        if self.thread is not threading.currentThread():
            self.thread.cancel()
            if not self.thread.daemon:
                self.thread.join()
        self.thread = None

    def graceful(self):
        """Stop the callback's background task thread and restart it."""
        self.stop()
        self.start()


class ThreadPoolMonitor(Monitor):
    """ThreadPoolMonitor for dynamic resizing."""

    def __init__(self, frequency, name=None):
        """Initialize ThreadPoolMonitor."""
        self._run = lambda: None
        self._resizer = None
        super(ThreadPoolMonitor, self).__init__(
            self.run,
            frequency=frequency,
            name=name,
        )

    def run(self):
        """Run the monitor."""
        self._run()

    def configure(self, thread_pool, minspare, maxspare, shrinkfreq):
        """Configure the pool resizer.

        :param thread_pool: ThreadPool object
        :param minspare: Minimum number of idle resources available.
        :param maxspare: Maximum number of idle resources available.
        :param shrinkfreq: Minimum seconds between shrink operations. Set to 0
                        to disable shrink checks.
        """
        self._resizer = DynamicPoolResizer(
            thread_pool,
            minspare,
            maxspare,
            shrinkfreq=shrinkfreq,
        )
        self._run = self._resizer.run

    def stop(self):
        """Stop the monitor."""
        self._run = lambda: None
        super(ThreadPoolMonitor, self).stop()
