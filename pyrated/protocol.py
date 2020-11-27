import asyncio


class MemcachedServerProtocol(asyncio.Protocol):
    _class_counter = 0

    @classmethod
    def create_class(cls, rlist, dynamic=False):
        """
        Allow use of distinct subclasses each sharing their own state

        """
        cls._class_counter += 1

        ret = type(cls.__name__ + str(cls._class_counter), (cls, ), {})
        ret.rlist = rlist
        ret.dynamic = dynamic

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
            data = 'VALUE %s 0 %d\r\n%s\r\n' % (key, len(value), value)
            self.transport.write(data.encode())

        self.transport.write(b'END\r\n')

    def handle_incr(self, key, noreply=None, *args):
        if not self.dynamic:
            rlist = self.rlist
        else:
            rlist, key = self.rlist.dynlist(key)

        ret = b'0' if rlist.hit(key) else b'1'

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
