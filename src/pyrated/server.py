import asyncio
import signal
import sys

import functools
from pyrated.ratelimit import RatelimitList


class MemcachedServerProtocol(asyncio.Protocol):
    _class_counter = 0

    @classmethod
    def create_class(cls):
        """
        Allow use of distinct subclasses each sharing their own state

        """
        cls._class_counter += 1

        ret = type(cls.__name__ + str(cls._class_counter), (cls, ), {})
        ret.rlist = RatelimitList(10, 5)

        return ret

    def connection_made(self, transport):
        self.transport = transport
        self.buffer = b''

        # remote = transport.get_extra_info('peername')[0]

    def handle_line(self, line):
        command, *args = line.split(' ')

        print('Command: {}, args={!r}'.format(command, []))

        if command == 'incr':
            return self.handle_incr(*args)

        if command == 'get':
            return self.handle_get(*args)

        if command == 'delete':
            return self.handle_delete(*args)

        self.transport.write(b'ERROR unknown command\r\n')

    def handle_get(self, *keys):
        lines = []
        for key in filter(self.rlist.__contains__, keys):
            value = str(self.rlist.get(key))
            lines.append('VALUE %s 0 %d %s' % (key, len(value), value))

        self.transport.write('\r\n'.join(lines).encode() + b'\r\nEND\r\n')

    def handle_incr(self, key, value=0, noreply=None, *args):
        ret = b'0' if self.rlist.hit(key) else b'1'

        if noreply == 'noreply':
            return

        self.transport.write(ret + b'\r\n')


    def handle_delete(self, key, noreply=None):
        print("delete", key)
        removed = self.rlist.remove(key)

        if noreply == 'noreply':
            return

        if removed:
            self.transport.write(b'DELETED\r\n')
        else:
            self.transport.write(b'NOT_FOUND\r\n')


    def data_received(self, data):
        #print('got {} bytes: {}, last={!r}'.format(len(data), data[0:20], data[-1]))

        lines = (self.buffer + data).split(b'\n')

        for line in lines[:-1]:
            # XXX try except?
            self.handle_line(line.rstrip().decode())

        # '' in most cases, data left to read in others
        self.buffer = lines[-1]

        # That's a very big line, cut connection
        if len(self.buffer) > 8096:
            self.transport.close()
        
        return


def sighandle(loop, server):
    def sigquit(signal, *args):
        server.close()
        loop.run_until_complete(server.wait_closed())
        loop.close()
        sys.exit()

    signal.signal(signal.SIGTERM, sigquit)
    signal.signal(signal.SIGINT, sigquit)

def quit(loop, server, rlist):
    loop.call_soon(loop.stop)

def main():
    loop = asyncio.get_event_loop()
    # Each client connection will create a new protocol instance
    protocol_class = MemcachedServerProtocol.create_class()

    coro = loop.create_server(protocol_class, '', 11211)

    server = loop.run_until_complete(coro)
    print('Serving on ' + ', '.join(str(sock.getsockname())
                                   for sock in server.sockets))


    # Serve requests until Ctrl+C is pressed
    protocol_class.rlist.install_cleanup(loop)
    pquit = functools.partial(quit, loop, server, protocol_class.rlist)

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