import asyncio

import pytest
from pyrated.ratelimit import Ratelimit
from pyrated.server import MemcachedServerProtocol


@pytest.fixture()
async def fake_server(event_loop, unused_tcp_port):
    protocol = MemcachedServerProtocol.create_class(Ratelimit(1, 2))
    create_server = event_loop.create_server(protocol, '127.0.0.1',
                                             unused_tcp_port)
    server = await create_server
    yield server
    server.close()
    await server.wait_closed()


@pytest.fixture()
async def client(event_loop, fake_server, unused_tcp_port):
    print('fake', fake_server)
    yield await asyncio.open_connection('127.0.0.1', unused_tcp_port,
                                        loop=event_loop)


async def read(reader):
    ret = b''

    while True:
        coro = reader.read(1)
        try:
            ret += await asyncio.wait_for(coro, timeout=0.001)
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

    async def delete_noreply(self):
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
