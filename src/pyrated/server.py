import asyncio
import signal
import sys

import functools
from pyrated.rlist import RatelimitList


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

        remote = transport.get_extra_info('peername')[0]
        print('New connection from {}'.format(remote))

    def handle_line(self, line):
        command, *args = line.split(' ')

        print('Command: {}, args={!r}'.format(command, []))

        if command == 'get':
            return self.handle_get(*args)

        if command == 'incr':
            return self.handle_incr(*args)

        if command == 'delete':
            return self.handle_delete(*args)

        self.transport.write(b'ERROR unknown command\r\n')


    def handle_get(self, *keys):
        print("get", ', '.join(keys))

        sendback = ''
        for key in set(keys).intersection(self.rlist):
            value = str(self.rlist.get(key))
            sendback += 'VALUE %s 0 %d %s\r\n' % (key, len(value), value)
        self.transport.write((sendback + 'END\r\n').encode())

    def handle_incr(self, key, *args):
        print("incr", key)

        ret = b'0' if self.rlist.hit(key) else b'1'

        self.transport.write(ret + b'\r\n')


    def handle_delete(self, key, noreply=None):
        print("delete", key)

        if self.rlist.remove(key):
            self.transport.write(b'DELETED\r\n')
        else:
            self.transport.write(b'NOT_FOUND\r\n')



    def data_received(self, data):
        #print('got {} bytes: {}, last={!r}'.format(len(data), data[0:20], data[-1]))

        lines = (self.buffer + data).split(b'\n')

        for line in lines[:-1]:
            self.handle_line(line.rstrip().decode())

        # '' in most cases, data left to read in others
        self.buffer = lines[-1]
        
        return
        for line in data.decode().rstrip().split('\n'):
            try:
                line = line.rstrip()
                if not line:
                    self.transport.write(b'ERROR')
                    continue

                command, key, *args = line.split(' ', 2)

                print('Command {} with {}'.format(command, key))
                if command == 'incr':
                    self.transport.write(b'0\r\n')
                    continue
                self.transport.write(b'ERROR ?')
            except Exception as err:
                print('ERROR %r' % err)
                self.transport.write(b'SERVER_ERROR Internal server error\r\n')
                raise


def sighandle(loop, server):
    def sigquit(signal, *args):
        server.close()
        loop.run_until_complete(server.wait_closed())
        loop.close()
        sys.exit()

    signal.signal(signal.SIGTERM, sigquit)
    signal.signal(signal.SIGINT, sigquit)

def quit(loop, server):
    server.close()
    loop.call_soon(server.wait_closed)
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

    # sighandle(loop, server)
    pquit = functools.partial(quit, loop, server)
    loop.add_signal_handler(signal.SIGINT, pquit)
    loop.add_signal_handler(signal.SIGINT, pquit)

    try:
        loop.run_forever()
    finally:
        loop.close()
    return

    # Close the server
    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()

if __name__ == '__main__':
    main()