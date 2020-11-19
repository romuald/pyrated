import weakref
import pickle
import asyncio

from time import sleep

import pytest

from pyrated.ratelimit import Ratelimit


def test_actual_time():
    # A test without FakeTime

    # 10 hits in 100ms
    rl = Ratelimit(10, 0.1)

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

def test_static_time(faketime):
    # 15 hits in 10 seconds
    rl = Ratelimit(15, 10)

    # 10 hits are okay
    for _ in range(15):
        assert rl.hit('a-key') is True
        assert rl.hit('another-key') is True

    # 11th hit fails
    assert rl.hit('a-key') is False
    assert rl.hit('another-key') is False

    faketime += 10000

    for _ in range(10):
        assert rl.hit('a-key') is True
        assert rl.hit('another-key') is True

def test_sliding_time(faketime):
    # 2 hits per second
    rl = Ratelimit(2, 1)


    assert rl.hit('key') is True

    faketime += 100
    assert rl.hit('key') is True

    for _ in range(9):
        assert rl.hit('key') is False
        faketime += 100

    assert rl.hit('key') is True
    assert rl.hit('key') is False


def test_cleanup(faketime):
    # 5 hits accross 10 seconds
    rl = Ratelimit(5, 10)

    rl.hit('first')
    rl.hit('second')

    faketime += 1000

    rl.hit('second')
    rl.hit('third')

    faketime += 8999
    rl.cleanup()
    assert len(rl) == 3

    faketime += 1
    rl.cleanup()
    assert len(rl) == 2
    assert 'first' not in rl

    faketime += 1000
    rl.hit('third')
    rl.cleanup()
    assert len(rl) == 1
    assert 'second' not in rl

    faketime += 10000
    rl.cleanup()
    assert len(rl) == 0


def test_cleanup_rollover(faketime):
    rl = Ratelimit(100, 10)
    last = None  # last succesful hit (which determine expiration time)

    for _ in range(500):
        faketime += 10
        if rl.hit('foo'):
            last = faketime.value
        rl.cleanup()
        assert len(rl) == 1

    faketime.value = last + 9999
    rl.cleanup()
    assert len(rl) == 1

    faketime += 1
    rl.cleanup()
    assert len(rl) == 0


def test_time_rebase(faketime):
    # Test that the internal "rebase" of time base works
    # (avoid uint32 overflow)
    # The maximum milliseconds storable in an uint32 is about 49 days
    HALFDAY = int((86400 * 1000) / 2)

    # 2 hits per day, for 70 days
    rl = Ratelimit(2, HALFDAY * 2 / 1000)

    for i in range(70):
        # first hit of the day works
        assert rl.hit('foo') is True
        faketime += HALFDAY

        # second hit 12 hours after works
        assert rl.hit('foo') is True
        faketime += 1000

        # Third hit 1 second after doesn't
        assert rl.hit('foo') is False
        faketime += HALFDAY - 1000

def test_next_hit(faketime):
    # 10 hits over 10 seconds
    rl = Ratelimit(10, 10)

    # Single hit every 100ms for one second
    for i in range(10):
        assert rl.next_hit('woot') == 0
        assert rl.hit('woot') is True

        faketime += 100

    # Can't hit at 1000ms
    assert rl.hit('woot') is False

    # We have to wait 9 seconds
    assert rl.next_hit('woot') == 9000

    # 500ms after that we have to wait 8.5 seoncds
    faketime += 500
    assert rl.next_hit('woot') == 8500

    # 8.5 seconds after that we don't have to wait
    faketime += 8500
    assert rl.next_hit('woot') == 0

    # Hitting 50ms after
    faketime += 50
    assert rl.hit('woot') is True

    # We then have to wait 50ms again for the next hit
    assert rl.next_hit('woot') == 50
    faketime += 50

    assert rl.next_hit('woot') == 0
    assert rl.hit('woot') is True

def test_serialization(faketime):
    base = Ratelimit(10, 10)

    for i in range(9):
        assert base.hit('foo') is True
        faketime += 10

    copy = pickle.loads(pickle.dumps(base))

    # The 2 objects are distinct
    assert base.hit('foo') is True
    assert base.hit('foo') is False

    assert copy.hit('foo') is True
    assert copy.hit('foo') is False

    base.hit('bar')
    assert 'bar' in base
    assert 'bar' not in copy

def test_block_size():
    base = Ratelimit(10, 10)

    base.block_size = 5
    assert base.block_size == 5

    # Currently there is no upper bound, restriction
    # since the implementation won't over-allocate

    with pytest.raises(TypeError):
        base.block_size = 'foo'

    with pytest.raises(TypeError):
        base.block_size = 0.5

    with pytest.raises(ValueError):
        base.block_size = -29

def test_cleanup_reference():
    # deleting the last reference to an object will stop the cleanup task

    def task_count(loop):
        # Task.all_tasks deprecated, but
        # asyncio.all_tasks introduced in python 3.7
        try:
            return len(asyncio.all_tasks(loop))
        except AttributeError:
            return len(asyncio.Task.all_tasks(loop))

    loop = asyncio.new_event_loop()

    rl = Ratelimit(10, 10)
    ref = weakref.ref(rl)

    rl.install_cleanup(loop, 0.005)

    loop.run_until_complete(asyncio.sleep(0.01))
    assert task_count(loop) == 1

    del rl
    loop.run_until_complete(asyncio.sleep(0.02))

    assert ref() is None
    assert task_count(loop) == 0
