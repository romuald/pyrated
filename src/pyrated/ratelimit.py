import math
import asyncio

from ._ratelimit import RatelimitBase


class Ratelimit(RatelimitBase):
    """Not actually a list"""

    def __init__(self, count, delay, block_size=0.20):
        """
        :param count: max number of hits for an entry of the list
        :param delay: in seconds, the period in which each entry is limited
        :param block_size: by how much the memory will be allocated for each
            entry, defaults to a fifth of the maximum memory used
            Meaning at "worst" 5 memory allocations, or at "worst" a fifth
            of the memory wasted, depending on your point of view

        """
        self._entries = {}

        if count <= 0:
            raise ValueError('count must be greater than 0 (%d)' % count)

        if delay <= 0:
            raise ValueError('delay must be greater than 0 (%d)' % delay)

        if delay > 86400 * 45:
            raise ValueError('maximum delay is 45 days (%d)' % delay)

        if isinstance(block_size, float) and block_size <= 1.0:
            self.block_size = math.ceil(count * block_size)
        else:
            self.block_size = block_size

        self._count = count
        self._delay = int(delay * 1000)
        self._cleanup_task = None

    @property
    def count(self):
        """
        Number of hits per period allowed by this list

        """
        return self._count

    @property
    def delay(self):
        """
        Time frame in which hits are are allowed

        """
        return float(self._delay) / 1000

    @property
    def block_size(self):
        """
        Size of memory pre-allocations

        For example a block size of 10 for a list of 25 will
        allocate 10 slots on the first hit, 10 new more on the 11th hit,
        and finally 5 slots on the 21th hit

        """

        return self._block_size

    @block_size.setter
    def block_size(self, value):
        if not isinstance(value, int):
            raise TypeError('block_size is integer only')

        if value <= 0:
            raise ValueError('block_size must be greater than 0')

        self._block_size = int(value)

    def __iter__(self):
        return iter(self._entries)

    def __contains__(self, key):
        return key in self._entries

    def __len__(self):
        return len(self._entries)

    def remove(self, entry):
        return bool(self._entries.pop(entry, False))

    def __getstate__(self):
        ret = {
            '_count': self._count,
            '_delay': self._delay,
            '_block_size': self._block_size,
            '_entries': self._entries,
        }

        return ret

    def __setstate__(self, state):
        self._count = state['_count']
        self._delay = state['_delay']
        self._block_size = state['_block_size']
        self._entries = state['_entries']

    def install_cleanup(self, loop, interval=30.0):
        """
        Install a cleanup task (periodical) in an asyncio loop,
        running every interval seconds

        """
        if interval < 0:
            raise ValueError('Interval must be positive')

        if self._cleanup_task is not None:
            self._cleanup_task.cancel()

        self._cleanup_task = loop.create_task(self.cleanup_run(interval))

        return self._cleanup_task

    def remove_cleanup(self):
        """
        Remove/cancel the current cleanup task

        """
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None

    @asyncio.coroutine
    def cleanup_run(self, interval):
        """
        Running task of the install_cleanup method, do a cleanup of the list
        every *interval* seconds
        """
        while True:
            try:
                yield from asyncio.sleep(interval)

                self.cleanup()

            except asyncio.CancelledError:
                break
