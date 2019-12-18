# -*- coding: utf-8 -*-
"""Dynamic pool.

`dynpool <https://tabo.pe/projects/dynpool/>`_ is a Python
library that handles the growing and shrinking of a pool
of resources depending on usage patterns,
written by `Gustavo Picón <https://tabo.pe/>`_ and
licensed under the Apache License 2.0.

``dynpool`` doesn't handle pools directly, and has no
concept of connections, threads or processes. That should be
dealt in a provided pool object. ``dynpool`` only handles
the growing and shrinking of resources in the given pool
object, and for that, the pool must follow an interface:


.. py:class:: PoolInterface


   .. py:attribute:: size

      The number of resources in the pool at the moment. Includes
      idle and used resources.

   .. py:attribute:: idle

      The number of idle resources in the pool at the moment.
      ``dynpool`` will either :py:meth:`grow` or :py:meth:`shrink`
      idle resources depending on the values of
      `minspare` and `maxspare` in :py:class:`dynpool.DynamicPoolResizer`.

   .. py:attribute:: min

      The minimum number of resources that should be in the pool.
      ``dynpool`` will :py:meth:`grow` the pool if :py:attr:`size`
      is lower than this value.


   .. py:attribute:: max

      The maximum number of resources that should be in the pool.
      ``dynpool`` won't grow the pool beyond this point, and will
      try to :py:meth:`shrink` it as soon as resources are freed.

      If max has a negative value, there won't be a limit for
      resource growth.

   .. py:attribute:: qsize

      The size of the incoming jobs queue that will be handled by
      idle resources.

   .. py:method:: grow(amount)

      Creates ``amount`` new idle resources in the pool.

   .. py:method:: shrink(amount)

      Shrinks the pool by ``amount`` resources.


Example

.. code-block:: python

    import dynpool
    from example_code import SomeThreadPool, run_periodically

    # A user provided thread pool that follows the interface
    # expected by DynamicPoolResizer.
    pool = SomeThreadPool(min=3, max=30)

    # We create a thread pool monitor.
    monitor = dynpool.DynamicPoolResizer(pool, minspare=5, maxspare=10)

    # Creating a thread pool monitor does nothing. We need to
    # call it's run() method periodically. Let's do it every second.
    run_periodically(monitor.run, interval=1)


"""

import math
import threading
import time
import functools


def non_repeating(method):
    """Non repeating.

    Decorate a function such that it's behavior is only invoked
    when the parameters differ from the last call. This
    function could be implemented with jaraco.functools
    and backports.functools_lru_cache as so:

    cache = functools.partial(lru_cache, maxsize=1)
    non_repeating = functools.partial(method_cache, cache_wrapper=cache)

    >>> x = []
    >>> @non_repeating
    ... def add_item(self, val):
    ...     x.append(val)
    >>> add_item(None, 1)
    >>> add_item(None, 2)
    >>> add_item(None, 2)
    >>> add_item(None, 3)
    >>> add_item(None, 2)
    >>> x
    [1, 2, 3, 2]
    """
    last = []

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        params = [args, kwargs]
        if last == params:
            return
        last[:] = params
        return method(self, *args, **kwargs)

    return wrapper


class DynamicPoolResizer(object):
    """Grow or shrink a pool of resources depending on usage patterns.

    :param pool: Pool object that follows the expected interface.
    :param minspare: Minimum number of idle resources available.
    :param maxspare: Maximum number of idle resources available.
    :param shrinkfreq: Minimum seconds between shrink operations. Set to 0
                       to disable shrink checks.
    :param logfreq: Minimum seconds between status logging. Set to 0 to disable
                    status logging (which is the default).
    :param logger: Callback that will act as a logger. There is no
                   logging by default
    :param mutex: Mutex used in :py:meth:`run()`.
                  A `threading.Lock()` object will be used by default.

    You can set the frequency values to 0 to disable them.
    """

    def __init__(
        self,
        pool,
        minspare,
        maxspare,
        shrinkfreq=5,
        logfreq=0,
        logger=None,
        mutex=None,
    ):
        """Initialize pool."""
        self.pool = pool
        self.minspare = minspare
        self.maxspare = maxspare
        self.shrinkfreq = shrinkfreq
        self.logfreq = logfreq
        self.log = logger or (lambda msg: None)
        self.lastshrink = None
        self.lastlog = None
        self._mutex = mutex or threading.Lock()

    def run(self):
        """Perform maintenance operations.

        This method should be called periodically by a running application.
        """
        with self._mutex:
            grow_value = self.grow_value
            if grow_value:
                self.grow(grow_value)
            elif self.can_shrink():
                shrink_value = self.shrink_value
                if shrink_value:
                    self.shrink(shrink_value)
            if self.can_log():
                self.queue_log()
                self.lastlog = time.time()

    def queue_log(self, msg=''):
        """Queue log."""
        pool = self.pool
        self._log_if_new(pool.size, pool.idle, pool.qsize, msg)

    @non_repeating
    def _log_if_new(self, pool_size, pool_idle, pool_qsize, msg):
        """Log message.

        Log the message, but as the result is cached, if the parameters
        are the same as the last call, the behavior is bypassed.
        """
        self.log('Thread pool: [current={0}/idle={1}/queue={2}]{3}'.format(
            pool_size, pool_idle, pool_qsize, msg,
        ))

    def action_log(self, action, amount):
        """Log an action."""
        self.queue_log(' {0} by {1}'.format(action, amount))

    @property
    def grow_value(self):
        """Get grow val."""
        pool = self.pool
        pool_size = pool.size
        pool_min = pool.min
        pool_max = pool.max
        pool_idle = pool.idle
        pool_qsize = pool.qsize
        maxspare = self.maxspare
        minspare = self.minspare

        if 0 < pool_max <= pool_size or pool_idle > maxspare:
            growby = 0
        elif not pool_idle and pool_qsize:
            # UH OH, we don't have available threads to continue serving the
            # queue. This means that we just received a lot of requests that we
            # couldn't handle with our usual minspare threads value.
            #
            # So spawn enough threads such that we can cope with the
            # number of waiting requests, and satisfy the minspare
            # requirement at the same time (while adhering to the
            # maximum number of threads).
            if pool_max > 0:
                growby = min(pool_qsize + minspare, pool_max - pool_size)
            else:
                # If we have no maximum defined, then don't try to factor
                # pool_max into the equation.
                growby = pool_qsize + minspare
        else:
            growby = max(0, pool_min - pool_size, self.minspare - pool_idle)
        return growby

    def grow(self, growby):
        """Grow the pool."""
        self.action_log('Growing', growby)
        self.pool.grow(growby)

    def can_shrink(self):
        """Can the pool be shrinked."""
        return (self.shrinkfreq
                and (
                    not self.lastshrink
                    or time.time() - self.lastshrink > self.shrinkfreq
                ))

    def can_log(self):
        """Can we log."""
        return (self.logfreq > 0
                and (
                    not self.lastlog
                    or time.time() - self.lastlog > self.logfreq
                ))

    @property
    def shrink_value(self):
        """Get shrink value for the pool."""
        pool = self.pool
        pool_size = pool.size
        pool_min = pool.min
        pool_idle = pool.idle
        pool_qsize = pool.qsize
        minspare = self.minspare
        if pool_size <= pool_min:
            # Never shrink below the min value
            shrinkby = 0
        elif pool_size == pool_idle and not pool_qsize:
            # It's oh so quiet...
            # All the threads are idle and there are no incoming requests.
            # We go down to our initial threadpool size.
            shrinkby = min(pool_size - pool_min, pool_idle - minspare)
        elif pool_idle > self.maxspare:
            # Leave only maxspare idle threads ready to accept connections.
            shrinkby = pool_idle - self.maxspare
        elif pool_idle > minspare + 1 and not pool_qsize:
            # We have more than minspare threads idling, but no incoming
            # connections to handle. Slowly shrink the thread pool by half
            # every time the Thread monitor runs (as long as there are no
            # incoming connections).
            #
            # But make sure that we have one more thread than
            # minspare to prevent creating another thread as soon as
            # a request comes in.
            shrinkby = int(math.ceil((pool_idle - minspare) / 2.0))
        else:
            shrinkby = 0
        return shrinkby

    def shrink(self, shrinkby):
        """Shrink the pool."""
        self.action_log('Shrinking', shrinkby)
        self.pool.shrink(shrinkby)
        self.lastshrink = time.time()
