import asyncio

import pytest
from pyrated.ratelimit import Ratelimit
from pyrated.server import MemcachedServerProtocol


@pytest.fixture()
def fake_server(event_loop, unused_tcp_port):
    protocol = MemcachedServerProtocol.create_class(Ratelimit(1, 2))
    create_server = event_loop.create_server(protocol, '127.0.0.1',
                                             unused_tcp_port)
    server = event_loop.run_until_complete(create_server)
    yield server
    server.close()
    event_loop.run_until_complete(server.wait_closed())


@pytest.fixture()
def client(event_loop, fake_server, unused_tcp_port):
    yield event_loop.run_until_complete(
        asyncio.open_connection('127.0.0.1', unused_tcp_port,
                                loop=event_loop))


async def read(reader):
    ret = b''

    while True:
        coro = reader.read(1)
        try:
            ret += await asyncio.wait_for(coro, timeout=0.01)
        except asyncio.TimeoutError:
            break

    return ret


@pytest.mark.asyncio
class TestProtocol:
    async def test_get_empty(self, client):
        reader, writer = client
        writer.write(b'get foo\r\n')

        res = await read(reader)
        assert res == b'END\r\n'

    async def test_incr(self, client):
        reader, writer = client

        # first call is allowed
        writer.write(b'incr foo\r\n')
        res = await read(reader)
        assert res == b'0\r\n'

        # second call is blocked
        writer.write(b'incr foo\r\n')
        res = await read(reader)
        assert res == b'1\r\n'

    async def test_get_multiple(self, client):
        reader, writer = client

        # first call is allowed
        writer.write(b'incr foo\r\nincr bar\r\n')
        res = await read(reader)
        assert res == b'0\r\n0\r\n'

        # second call is blocked
        writer.write(b'incr foo\r\nincr baz\r\nincr bar\r\n')
        res = await read(reader)
        assert res == b'1\r\n0\r\n1\r\n'

        writer.write(b'get foo bar baz qux\r\n')

        res = await read(reader)
        res = res.decode()

        lines = res.split('\r\n')
        assert len(lines) == 8

        assert lines[0].startswith('VALUE foo 0')
        value = float(lines[1])
        assert 1.9 < value < 2.0

        assert lines[2].startswith('VALUE bar 0')
        value = float(lines[3])
        assert 1.9 < value < 2.0

        assert lines[4].startswith('VALUE baz 0')
        value = float(lines[5])
        assert 1.9 < value < 2.0

        assert lines[6] == 'END'

    async def test_get_incr_noreply(self, client):
        reader, writer = client

        # first don't reply
        writer.write(b'incr foo noreply\r\n')
        res = await read(reader)
        assert res == b''

        # second call is blocked
        writer.write(b'incr foo\r\n')
        res = await read(reader)
        assert res == b'1\r\n'

    async def test_delete(self, client):
        reader, writer = client

        writer.write(b'incr foo\r\nincr bar\r\n')
        res = await read(reader)
        assert res == b'0\r\n0\r\n'

        writer.write(b'delete foo\r\n')
        res = await read(reader)
        assert res == b'DELETED\r\n'

        writer.write(b'incr foo\r\nincr bar\r\n')
        res = await read(reader)
        assert res == b'0\r\n1\r\n'

        writer.write(b'delete baz\r\n')
        res = await read(reader)
        assert res == b'NOT_FOUND\r\n'

    async def test_delete_noreply(self, client):
        reader, writer = client

        writer.write(b'incr foo\r\n')
        res = await read(reader)
        assert res == b'0\r\n'

        writer.write(b'delete foo noreply\r\n')
        res = await read(reader)
        assert res == b''

        writer.write(b'incr foo\r\n')
        res = await read(reader)
        assert res == b'0\r\n'

    async def test_set(self, client):
        reader, writer = client

        writer.write(b'set foo 0 0 3\r\n')
        res = await read(reader)
        assert res == b'ERROR unknown command\r\n'

    async def test_big_line(self, client):
        reader, writer = client

        data = 'incr ' + ('b' * 270000) + '\r\n'
        writer.write(data.encode())

        with pytest.raises(ConnectionResetError):
            await read(reader)


def test_create_protocol_class():
    rl1 = Ratelimit(1, 2)
    rl2 = Ratelimit(1, 3)

    cls1 = MemcachedServerProtocol.create_class(rl1)
    cls2 = MemcachedServerProtocol.create_class(rl2)

    assert cls1.rlist is not cls2.rlist
