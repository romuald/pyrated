import weakref
import pytest

from pyrated.ratelimit import Ratelimit
from .utils import FakeTime


def test_no_spec():
    # list without spec
    rl = Ratelimit(10, 10)

    lst, key = rl.dynlist('example')
    assert lst is rl
    assert key == 'example'


def test_no_key():
    # key is empty (may need fix)
    rl = Ratelimit(10, 10)

    lst, key = rl.dynlist('1/2:')

    assert lst is not rl
    assert key == ''


def test_ok():
    # same format will return the same list object,
    # each list has the correct settings
    rl = Ratelimit(8, 10)

    lst1, key1 = rl.dynlist('1/4:foo')
    lst2, key2 = rl.dynlist('1/4:bar')
    lst3, key3 = rl.dynlist('3/6:baz')

    assert lst1 is lst2
    assert lst1 is not lst3

    assert key1 == 'foo'
    assert key2 == 'bar'
    assert key3 == 'baz'

    assert rl.count == 8
    assert rl.period == 10

    assert lst1.count == 1
    assert lst1.period == 4
    assert lst3.count == 3
    assert lst3.period == 6


@pytest.mark.parametrize('fmt',
    ('1/2', '-1/10:b' , '1/-20:a', '0/20:d', '20/0:d',
     '2147483656/1:x', '1/2147483656:y',
    ))
def test_bad_formats(fmt):
    rl = Ratelimit(10, 10)

    lst, key = rl.dynlist(fmt)

    assert lst is rl
    assert key == fmt


def test_cleanup():
    import gc
    rl = Ratelimit(2, 10)
    subrl, _ = rl.dynlist('3/2:unused')

    with FakeTime() as fake:

        rl.hit('a')
        subrl.hit('a')

        fake += 1000
        rl.hit('b')
        subrl.hit('b')

        rl.cleanup()

        assert len(rl) == 2
        assert len(subrl) == 2

        fake += 1000

        rl.cleanup()
        assert len(rl) == 2
        assert len(subrl) == 1

        fake += 1100

        rl.cleanup()

    assert len(subrl) == 0
    assert len(rl._dlists) == 0

    ref = weakref.ref(subrl)
    del subrl

    # no leak
    assert ref() is None
