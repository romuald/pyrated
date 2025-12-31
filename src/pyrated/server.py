import argparse
import asyncio
import re
import signal
import sys
from typing import Coroutine

from .protocol import MemcachedServerProtocol
from .ratelimit import Ratelimit


class RatelimitDef:
    """
    Ratelimit defintition parsing
        - 1/8 -> max 1 hit in 8 seconds
        - 5/5 -> max 5 hits in 5 seconds
        - 5/1m -> max 5 hits in one minute

    """

    def __init__(self, value):
        reg = r"(\d+)/(\d+)([mhd])?"
        match = re.match(reg, value)
        if not match:
            raise ValueError

        self.count = int(match.group(1))
        self.period = int(match.group(2))

        if match.group(3) == "m":
            self.period *= 60
        elif match.group(3) == "h":
            self.period *= 3600
        elif match.group(3) == "d":
            self.period *= 86400

    def __repr__(self):
        return "%r/%r" % (self.count, self.period)


def run_in_loop(coro: Coroutine) -> asyncio.Task:  # pragma: no cover
    """
    Shorthand method to run a coroutine from "non-async" code

    SIGTERM/SIGINT will cancel the task

    Returns the task that was created from the coroutine

    """

    loop = asyncio.new_event_loop()
    task = asyncio.ensure_future(coro, loop=loop)
    loop.add_signal_handler(signal.SIGTERM, task.cancel)
    loop.add_signal_handler(signal.SIGINT, task.cancel)
    loop.run_until_complete(task)

    return task


def parse_args(args):
    parser = argparse.ArgumentParser(description="python ratelimit daemon")
    parser.add_argument(
        "definition",
        type=RatelimitDef,
        help="The ratelimit definition ([#hits]/[period])",
    )
    parser.add_argument(
        "-s", "--source", action="append", help="IP address/host to listen to"
    )
    parser.add_argument(
        "-p", "--port", type=int, default=11211, help="TCP port to listen to"
    )

    args = parser.parse_args(args)

    # https://bugs.python.org/issue16399 -_-
    if args.source is None:
        args.source = ["localhost"]

    return args


async def close_on_cancel(server):
    """
    Workaround breaking change in python 3.12+

    Starting 3.12, serve_forever() will wait for clients to disconnect
    We don't want that so tell server to close clients

    """
    try:
        while True:
            await asyncio.sleep(1000)
    except asyncio.CancelledError:
        # only works starting 3.13+ unfortunately
        if hasattr(server, "close_clients"):
            server.close()
            server.close_clients()


async def amain(args):
    rlist = Ratelimit(args.definition.count, args.definition.period)
    protocol_class = MemcachedServerProtocol.create_class(rlist)

    loop = asyncio.get_running_loop()

    server = await loop.create_server(protocol_class, args.source, args.port)
    interfaces = (str(sock.getsockname()[0]) for sock in server.sockets)
    print("Serving on %s - port %d" % (", ".join(interfaces), args.port))

    protocol_class.rlist.install_cleanup(loop)
    canary = close_on_cancel(server)
    try:
        await asyncio.gather(server.serve_forever(), canary)
    except asyncio.CancelledError:
        pass
    finally:
        protocol_class.rlist.remove_cleanup()


def main():
    args = parse_args(sys.argv[1:])
    run_in_loop(amain(args))


if __name__ == "__main__":
    main()
