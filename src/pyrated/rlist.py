import asyncio

from .rentry import Rentry, now, cleanup_dict


class RatelimitList:
    """Not actually a list"""

    def __init__(self, count, delay):
        """
        :param count: max number of hits for an entry of the list
        :param delay: in seconds, the period in which each entry ist limited

        """
        self._entries = {}
        self._count = count
        self._delay = int(delay * 1000)
        self._cleanup_task = None

    @property
    def count(self):
        return self._count

    @property
    def delay(self):
        return float(self._delay) / 1000

    def __iter__(self):
        return iter(self._entries)

    def __contains__(self, key):
        return key in self._entries

    def __len__(self):
        return len(self._entries)

    def hit(self, key):
        entry = self._entries.get(key)

        if entry is None:
            entry = self._entries[key] = Rentry()

        return entry.hit(self._count, self._delay)

    def get(self, entry):
        return "XXX todo" # self._entries[entry]

    def remove(self, entry):
        return bool(self._entries.pop(entry, False))

    def install_cleanup(self, loop, interval=1.0):
        assert interval > 0
        self._cleanup_task = asyncio.ensure_future(self.cleanup_run(interval),
                                                   loop=loop)

        return self._cleanup_task

    def remove_cleanup(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None

    def cleanup(self):
        return cleanup_dict(self._entries, self._delay)

        nono = now()
        to_delete = set(key for key, value in self._entries.items()
                     if value.is_expired(nono, self._delay))

        for key in to_delete:
            del self._entries[key]
        #self._entries = {k: v for k, v in self._entries.items() if k not in to_delete}

        return len(to_delete)

    async def cleanup_run(self, interval):
        while True:
            try:
                await asyncio.sleep(interval)

                self.cleanup()

            except asyncio.CancelledError:
                break
            print('cleaning up')