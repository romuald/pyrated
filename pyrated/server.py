import re
import sys
import signal
import asyncio
import argparse
import functools


from pyrated.ratelimit import Ratelimit


class MemcachedServerProtocol(asyncio.Protocol):
    _class_counter = 0

    @classmethod
    def create_class(cls):
        """
        Allow use of distinct subclasses each sharing their own state

        """
        cls._class_counter += 1

        ret = type(cls.__name__ + str(cls._class_counter), (cls, ), {})

        return ret

    def connection_made(self, transport):
        self.transport = transport
        self.buffer = b''

    def handle_line(self, line):
        command, *args = line.split(' ')

        # print('Command: {}, args={!r}'.format(command, []))

        if command == 'incr':
            return self.handle_incr(*args)

        if command == 'get':
            return self.handle_get(*args)

        if command == 'delete':
            return self.handle_delete(*args)

        self.transport.write(b'ERROR unknown command\r\n')

    def handle_get(self, *keys):
        for key in filter(self.rlist.__contains__, keys):
            value = str(self.rlist.next_hit(key) / 1000)
            line = 'VALUE %s 0 %d\r\n%s' % (key, len(value), value)
            self.transport.write(line.encode())

        self.transport.write(b'END\r\n')

    def handle_incr(self, key, value=0, noreply=None, *args):
        ret = b'0' if self.rlist.hit(key) else b'1'

        if noreply == 'noreply':
            return

        self.transport.write(ret + b'\r\n')

    def handle_delete(self, key, noreply=None):
        removed = self.rlist.remove(key)

        if noreply == 'noreply':
            return

        if removed:
            self.transport.write(b'DELETED\r\n')
        else:
            self.transport.write(b'NOT_FOUND\r\n')

    def data_received(self, data):
        # print('got {} bytes: {}, last={!r}'.format(len(data),
        #                                            data[0:20], data[-1]))

        lines = (self.buffer + data).split(b'\n')

        for line in lines[:-1]:
            # XXX try except?
            self.handle_line(line.rstrip().decode())

        # '' in most cases, data left to read in others
        self.buffer = lines[-1]

        # That's a very big line, cut connection
        if len(self.buffer) > 8096:
            self.transport.close()


class RatelimitDef:
    """
    Ratelimit defintition parsing
        - 1/8 -> max 1 hit in 8 seconds
        - 5/5 -> max 5 hits in 5 seconds

    """

    def __init__(self, value):
        reg = r'(\d+)/(\d+)([mhd])?'
        match = re.match(reg, value)
        if not match:
            raise ValueError

        self.count = int(match.group(1))
        self.delay = int(match.group(2))

        if match.group(3) == 'm':
            self.delay *= 60
        elif match.group(3) == 'h':
            self.delay *= 3600
        elif match.group(3) == 'd':
            self.delay *= 86400

    def __repr__(self):
        return '%r/%r' % (self.count, self.delay)


def parse_args():
    parser = argparse.ArgumentParser(description='Foo')
    parser.add_argument('definition', type=RatelimitDef,
                        help='The ratelimit definition ([#hits]/[period])')
    parser.add_argument('-s', '--source', action='append',
                        help='IP address/host to listen to')
    parser.add_argument('-p', '--port', type=int, default=11211,
                        help='TCP port to listen to')

    args = parser.parse_args()

    # https://bugs.python.org/issue16399 -_-
    if args.source is None:
        args.source = ['localhost']

    return args


def main():
    args = parse_args()

    # Each client connection will create a new protocol instance
    protocol_class = MemcachedServerProtocol.create_class()
    protocol_class.rlist = Ratelimit(args.definition.count,
                                     args.definition.delay)

    loop = asyncio.get_event_loop()
    coro = loop.create_server(protocol_class, args.source, args.port)

    server = loop.run_until_complete(coro)
    interfaces = (str(sock.getsockname()[0]) for sock in server.sockets)
    print('Serving on %s - port %d' % (', '.join(interfaces), args.port))

    # Serve requests until Ctrl+C is pressed
    protocol_class.rlist.install_cleanup(loop)

    loop.add_signal_handler(signal.SIGINT, loop.stop)
    loop.add_signal_handler(signal.SIGTERM, loop.stop)

    try:
        loop.run_forever()
    finally:
        protocol_class.rlist.remove_cleanup()
        server.close()
        loop.run_until_complete(server.wait_closed())
        loop.close()


if __name__ == '__main__':
    main()
