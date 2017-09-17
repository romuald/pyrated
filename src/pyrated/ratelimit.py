import math
import asyncio

from ._ratelimit import RatelimitBase

class RatelimitList(RatelimitBase):
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
        return self._count

    @property
    def delay(self):
        return float(self._delay) / 1000

    @property
    def block_size(self):
        return self._block_size

    @block_size.setter
    def block_size(self, value):
        if value <= 0:
            raise ValueError('block_size must be greater than 0')

        self._block_size = value

    def __iter__(self):
        return iter(self._entries)

    def __contains__(self, key):
        return key in self._entries

    def __len__(self):
        return len(self._entries)

    def remove(self, entry):
        return bool(self._entries.pop(entry, False))

    def install_cleanup(self, loop, interval=30.0):
        if interval < 0:
            raise ValueError('Interval must be positive')

        self._cleanup_task = loop.create_task(self.cleanup_run(interval))

        return self._cleanup_task

    def remove_cleanup(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None

    @asyncio.coroutine
    def cleanup_run(self, interval):
        while True:
            try:
                yield from asyncio.sleep(interval)

                self.cleanup()

            except asyncio.CancelledError:
                break
