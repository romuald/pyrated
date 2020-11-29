import pytest

from pyrated._ratelimit import _set_fake_now, _get_fake_now


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "faketime(value): custom starting value for faketime fixture"
    )

@pytest.fixture
def faketime(request):
    marker = request.node.get_closest_marker("faketime")
    if marker is None:
        # Handle missing marker in some way...
        value = 1000
    else:
        value = int(marker.args[0])
    fake = FakeTime(value)
    with fake:
        yield fake


class FakeTime:
    """
    A wrapper object to fake the internal return of ratelimit's time() function

    It's a simple counter, units are milliseconds

    with FakeTime(42) as fake:
        fake.value += 10
        fake += 20

    """
    def __init__(self, value=1000):
        assert value > 1, "Fake time must be greater than 1 (ms)"

        self._value = value

    def __enter__(self):
        if _get_fake_now() != 0:
            raise RuntimeError('Unable to nest FakeTime')

        _set_fake_now(self._value)
        return self

    def __exit__(self, *junk):
        _set_fake_now(0)

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        assert value > 0, "Can only use positive fake time values"

        if _get_fake_now() != 0:
            assert value >= self.value, 'FakeTime can only increase value'
            _set_fake_now(value)
        self._value = value

    def __iadd__(self, value):
        self.value += value

        return self

    def __str__(self):
        return 'FakeTime at %d' % self.value
