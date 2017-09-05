from .rentry import Rentry


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

    def hit(self, key):
        entry = self._entries.get(key)

        if entry is None:
            entry = self._entries[key] = Rentry()

        return entry.hit(self._count, self._delay)

    def get(self, entry):
        return "XXX todo" # self._entries[entry]

    def remove(self, entry):
        return bool(self._entries.pop(entry, False))

    def gc(self):
        pass