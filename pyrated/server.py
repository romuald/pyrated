import re
import sys
import signal
import asyncio
import argparse
import functools


from .ratelimit import Ratelimit
from .protocol import MemcachedServerProtocol


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

    # Each client connection will create a new protocol instance,
    # but we need a shared state for all connections
    rlist = Ratelimit(args.definition.count, args.definition.delay)
    protocol_class = MemcachedServerProtocol.create_class(rlist)

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
