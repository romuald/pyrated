import asyncio

import pytest

from pyrated.server import amain, parse_args


def test_no_args(capsys):
    with pytest.raises(SystemExit):
        parse_args([])

    captured = capsys.readouterr()
    err = captured.err
    assert err.startswith("usage: ")
    assert "the following arguments are required: definition" in err


def test_invalid_definition(capsys):
    with pytest.raises(SystemExit):
        parse_args(["foo"])

    captured = capsys.readouterr()
    err = captured.err

    assert "invalid RatelimitDef value" in err


def test_definition_seconds():
    args = parse_args(["25/1000"])

    assert args.definition.count == 25
    assert args.definition.period == 1000


def test_definition_minutes():
    args = parse_args(["18/20m"])

    assert args.definition.count == 18
    assert args.definition.period == 1200

    assert repr(args.definition) == "18/1200"


def test_definition_hours():
    args = parse_args(["180/2h"])

    assert args.definition.count == 180
    assert args.definition.period == 7200


def test_definition_days():
    args = parse_args(["1500/5d"])

    assert args.definition.count == 1500
    assert args.definition.period == 432000


def test_defaults():
    args = parse_args(["1/1"])
    assert args.source == ["localhost"]
    assert args.port == 11211


def test_source_set():
    args = parse_args(["1/1", "-s", "::1"])
    assert args.source == ["::1"]


def test_source_multiple():
    args = parse_args(["1/1", "-s", "::1", "-s", "192.168.0.3"])
    assert args.source == ["::1", "192.168.0.3"]


def test_source_port():
    args = parse_args(["1/1", "-p", "6700"])
    assert args.port == 6700


@pytest.mark.asyncio
async def test_server_main(unused_tcp_port):
    port = unused_tcp_port
    args = parse_args(["1/1", "-s", "localhost", "-p", str(port)])

    task = asyncio.create_task(amain(args))
    async with asyncio.timeout(1):
        await asyncio.sleep(0.05)

        reader, writer = await asyncio.open_connection("localhost", port)

        writer.write(b"incr hello\r\n")
        res = await reader.read(8)
        assert res == b"0\r\n"

        writer.write(b"incr hello\r\n")
        res = await reader.read(8)
        assert res == b"1\r\n"
        writer.close()

        task.cancel()
        await task
