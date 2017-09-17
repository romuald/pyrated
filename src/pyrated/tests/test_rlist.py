import unittest
from time import sleep

from pyrated.ratelimit import RatelimitList
from pyrated._ratelimit import _set_fake_now, _get_fake_now

class FakeTime:
    def __init__(self, value=1000):
        assert value > 0

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
        assert value > 0

        if _get_fake_now() != 0:
            assert value >= self.value, 'FakeTime can only increase value'
            _set_fake_now(value)
        self._value = value

    def __iadd__(self, value):
        self.value += value

        return self

    def __str__(self):
        return 'FakeTime at %d' % self.value


class TestRlist(unittest.TestCase):

    def test_actual_time(self):
        # A test without FakeTime

        # 10 hits in 100ms
        rl = RatelimitList(10, 0.1)

        # 10 hits are okay
        for _ in range(10):
            assert rl.hit('a-key') is True
            assert rl.hit('another-key') is True

        # 11th hit fails
        assert rl.hit('a-key') is False
        assert rl.hit('another-key') is False

        # Waiting the whole period we can go on again
        sleep(0.1)
        
        for _ in range(10):
            assert rl.hit('a-key') is True
            assert rl.hit('another-key') is True

    def test_static_time(self):
        # 15 hits in 10 seconds
        rl = RatelimitList(15, 10)

        with FakeTime() as fake:
            # 10 hits are okay
            for _ in range(15):
                assert rl.hit('a-key') is True
                assert rl.hit('another-key') is True


            # 11th hit fails
            assert rl.hit('a-key') is False
            assert rl.hit('another-key') is False

            fake.value += 10000

            for _ in range(10):
                assert rl.hit('a-key') is True
                assert rl.hit('another-key') is True
    
    def test_sliding_time(self):
        # 2 hits per second
        rl = RatelimitList(2, 1)

        with FakeTime() as fake:

            assert rl.hit('key') is True

            fake += 100
            assert rl.hit('key') is True

            for _ in range(9):
                assert rl.hit('key') is False
                fake += 100

            #fake += 99
            #assert rl.hit('key') is False

            #fake += 1
            assert rl.hit('key') is True
            assert rl.hit('key') is False

    def test_cleanup(self):
        # 5 hits accross 10 seconds
        rl = RatelimitList(5, 10)

        with FakeTime() as fake:
            rl.hit('first')
            rl.hit('second')

            fake += 1000

            rl.hit('second')
            rl.hit('third')

            fake += 8999
            rl.cleanup()
            assert len(rl) == 3

            fake += 1
            rl.cleanup()
            assert len(rl) == 2
            assert 'first' not in rl

            fake += 1000
            rl.hit('third')
            rl.cleanup()
            assert len(rl) == 1
            assert 'second' not in rl

            fake += 10000
            rl.cleanup()
            assert len(rl) == 0

    def test_cleanup_rollover(self):
        rl = RatelimitList(100, 10)
        last = None  # last succesful hit (which determine expiration time)

        with FakeTime() as fake:
            for _ in range(500):
                fake += 10
                if rl.hit('foo'):
                    last = fake.value
                rl.cleanup()
                assert len(rl) == 1

            fake.value = last + 9999
            rl.cleanup()
            assert len(rl) == 1

            fake.value += 1
            rl.cleanup()
            assert len(rl) == 0

    def test_time_rebase(self):
        # Test that the internal "rebase" of time base works
        # (avoid uint32 overflow)
        # The maximum milliseconds storable in a uint32 is around 49 days
        HALFDAY = int((86400 * 1000) / 2)

        # 2 hits per day, for 70 days
        rl = RatelimitList(2, HALFDAY * 2 / 1000)

        with FakeTime() as fake:
            for i in range(70):
                # first hit of the day works
                assert rl.hit('foo') is True
                fake += HALFDAY

                # second hit 12 hours after works
                assert rl.hit('foo') is True
                fake += 1000

                # Third hit 1 second after doesn't
                assert rl.hit('foo') is False
                fake += HALFDAY - 1000

    def test_next_hit(self):
        # 10 hits over 10 seconds
        rl = RatelimitList(10, 10)

        with FakeTime() as fake:
            # Single hit every 100ms for one second
            for i in range(10):
                assert rl.next_hit('woot') == 0
                assert rl.hit('woot') is True

                fake += 100

            # Can't hit at 1000ms
            assert rl.hit('woot') is False

            # We have to wait 9 seconds
            assert rl.next_hit('woot') == 9000

            # 500ms after that we have to wait 8.5 seoncds
            fake += 500
            assert rl.next_hit('woot') == 8500

            # 8.5 seconds after that we don't have to wait
            fake += 8500
            assert rl.next_hit('woot') == 0

            # Hitting 50ms after
            fake += 50
            assert rl.hit('woot') is True

            # We then have to wait 50ms again for the next hit
            assert rl.next_hit('woot') == 50
            fake += 50

            assert rl.next_hit('woot') == 0
            assert rl.hit('woot') is True