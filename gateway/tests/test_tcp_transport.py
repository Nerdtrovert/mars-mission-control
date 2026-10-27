"""Unit and integration tests for the Raspberry Pi Gateway TCP transport."""

import asyncio
import pytest

from gateway.tcp_transport import (
    InvalidEncodingError,
    LanderTCPTransport,
    OversizedLineError,
)


@pytest.mark.anyio
async def test_tcp_transport_opens_and_accepts_client():
    transport = LanderTCPTransport(host="127.0.0.1", port=0)
    await transport.open()
    try:
        assert transport.is_open() is False
        reader, writer = await asyncio.open_connection(transport.host, transport.port)
        # Give the accept loop a moment
        await asyncio.sleep(0.05)
        assert transport.is_open() is True
        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.05)
        assert transport.is_open() is False
    finally:
        await transport.close()


@pytest.mark.anyio
async def test_tcp_transport_reconnection_and_cleanup_guard():
    """Verify that cleanup from an old client handler does not close a newer connection."""
    transport = LanderTCPTransport(host="127.0.0.1", port=0)
    await transport.open()
    try:
        # Connect client 1
        reader1, writer1 = await asyncio.open_connection(transport.host, transport.port)
        await asyncio.sleep(0.05)
        assert transport.is_open() is True

        # Connect client 2 while client 1 is connected (reconnect / takeover)
        reader2, writer2 = await asyncio.open_connection(transport.host, transport.port)
        await asyncio.sleep(0.05)
        assert transport.is_open() is True

        # Client 1 closes now - its accept task cleanup must NOT clear client 2
        writer1.close()
        await writer1.wait_closed()
        await asyncio.sleep(0.05)

        # Transport should STILL be open with client 2
        assert transport.is_open() is True

        # Test writing to client 2
        await transport.write_line('{"type":"ping"}')
        line = await reader2.readline()
        assert line == b'{"type":"ping"}\n'

        # Client 2 closes
        writer2.close()
        await writer2.wait_closed()
        await asyncio.sleep(0.05)
        assert transport.is_open() is False
    finally:
        await transport.close()


@pytest.mark.anyio
async def test_tcp_transport_repeated_reconnect_cycles():
    """Verify multiple consecutive connect/disconnect cycles keep the server open."""
    transport = LanderTCPTransport(host="127.0.0.1", port=0)
    await transport.open()
    try:
        for _ in range(5):
            reader, writer = await asyncio.open_connection(transport.host, transport.port)
            await asyncio.sleep(0.02)
            assert transport.is_open() is True
            writer.write(b'{"type":"tick"}\n')
            await writer.drain()
            received = await transport.read_line(timeout=1.0)
            assert received == '{"type":"tick"}'
            writer.close()
            await writer.wait_closed()
            await asyncio.sleep(0.02)
            assert transport.is_open() is False
    finally:
        await transport.close()


@pytest.mark.anyio
async def test_tcp_transport_oversized_line_raises_error():
    transport = LanderTCPTransport(host="127.0.0.1", port=0)
    await transport.open()
    try:
        reader, writer = await asyncio.open_connection(transport.host, transport.port)
        await asyncio.sleep(0.02)

        # Write more than MAX_LINE_LENGTH (4096 bytes) without a newline
        oversized_payload = b"X" * (transport.MAX_LINE_LENGTH + 100) + b"\n"
        writer.write(oversized_payload)
        await writer.drain()

        with pytest.raises(OversizedLineError):
            await transport.read_line(timeout=1.0)

        writer.close()
        await writer.wait_closed()
    finally:
        await transport.close()


@pytest.mark.anyio
async def test_tcp_transport_invalid_utf8_raises_error():
    transport = LanderTCPTransport(host="127.0.0.1", port=0)
    await transport.open()
    try:
        reader, writer = await asyncio.open_connection(transport.host, transport.port)
        await asyncio.sleep(0.02)

        # Invalid UTF-8 bytes followed by newline
        writer.write(b"\xff\xfe\xfd\n")
        await writer.drain()

        with pytest.raises(InvalidEncodingError):
            await transport.read_line(timeout=1.0)

        writer.close()
        await writer.wait_closed()
    finally:
        await transport.close()


@pytest.mark.anyio
async def test_tcp_transport_eof_raises_connection_error():
    transport = LanderTCPTransport(host="127.0.0.1", port=0)
    await transport.open()
    try:
        reader, writer = await asyncio.open_connection(transport.host, transport.port)
        await asyncio.sleep(0.02)

        writer.close()
        await writer.wait_closed()

        with pytest.raises(ConnectionError):
            await transport.read_line(timeout=1.0)
    finally:
        await transport.close()
