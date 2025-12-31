import io
import unittest.mock

import pytest

from pyrated.ratelimit import Ratelimit
from pyrated.server import MemcachedServerProtocol


class TestProtocol:
    @pytest.fixture(autouse=True)
    def mock_protocol(self):
        protocol = MemcachedServerProtocol.create_class(Ratelimit(1, 2))

        self.mprotocol = protocol()
        self.mbuffer = io.BytesIO()

        mock = unittest.mock.Mock()
        mock.write = self.mbuffer.write

        self.mprotocol.connection_made(mock)

    def write(self, data):
        self.mprotocol.data_received(data)

    def read(self, reset=True):
        ret = self.mbuffer.getvalue()
        if reset:
            self.mbuffer.seek(0)
            self.mbuffer.truncate()
        return ret

    def test_get_empty(self):
        self.write(b"get foo\r\n")
        assert self.read() == b"END\r\n"

    def test_incr(self):
        # first call is allowed
        self.write(b"incr foo\r\n")

        assert self.read() == b"0\r\n"

        # second call is blocked
        self.write(b"incr foo\r\n")
        assert self.read() == b"1\r\n"

    def test_get_multiple(self):
        # first call is allowed
        self.write(b"incr foo\r\nincr bar\r\n")
        assert self.read() == b"0\r\n0\r\n"

        # second call is blocked
        self.write(b"incr foo\r\nincr baz\r\nincr bar\r\n")
        assert self.read() == b"1\r\n0\r\n1\r\n"

        self.write(b"get foo bar baz qux\r\n")

        res = self.read().decode()

        lines = res.split("\r\n")
        assert len(lines) == 8

        assert lines[0].startswith("VALUE foo 0")
        value = float(lines[1])
        assert 1.9 < value <= 2.0

        assert lines[2].startswith("VALUE bar 0")
        value = float(lines[3])
        assert 1.9 < value <= 2.0

        assert lines[4].startswith("VALUE baz 0")
        value = float(lines[5])
        assert 1.9 < value <= 2.0

        assert lines[6] == "END"

    def test_get_incr_noreply(self):
        # first don't reply
        self.write(b"incr foo noreply\r\n")
        assert self.read() == b""

        # second call is blocked
        self.write(b"incr foo\r\n")
        assert self.read() == b"1\r\n"

    def test_delete(self):
        self.write(b"incr foo\r\nincr bar\r\n")
        assert self.read() == b"0\r\n0\r\n"

        self.write(b"delete foo\r\n")
        assert self.read() == b"DELETED\r\n"

        self.write(b"incr foo\r\nincr bar\r\n")
        assert self.read() == b"0\r\n1\r\n"

        self.write(b"delete baz\r\n")
        assert self.read() == b"NOT_FOUND\r\n"

    def test_delete_noreply(self):
        self.write(b"incr foo\r\n")
        assert self.read() == b"0\r\n"

        self.write(b"delete foo noreply\r\n")
        assert self.read() == b""

        self.write(b"incr foo\r\n")
        assert self.read() == b"0\r\n"

    def test_set(self):
        self.write(b"set foo 0 0 3\r\n")
        assert self.read() == b"ERROR unknown command\r\n"

    def test_big_line(self):
        data = "incr " + ("b" * 10000)
        self.write(data.encode())

        self.mprotocol.transport.close.assert_called_with()


def test_create_protocol_class():
    rl1 = Ratelimit(1, 2)
    rl2 = Ratelimit(1, 3)

    cls1 = MemcachedServerProtocol.create_class(rl1)
    cls2 = MemcachedServerProtocol.create_class(rl2)

    assert cls1.rlist is not cls2.rlist
