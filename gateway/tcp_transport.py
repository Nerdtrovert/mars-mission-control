"""TCP server transport for the lander ESP32's Wi-Fi telemetry connection."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TransportError(ConnectionError):
    """Base exception for lander transport errors."""


class OversizedLineError(TransportError):
    """Raised when an incoming line exceeds the maximum permitted byte length."""


class InvalidEncodingError(TransportError):
    """Raised when incoming message bytes cannot be decoded as valid UTF-8."""


class LanderTCPTransport:
    """Accept one ESP32 client and carry newline-delimited JSON both ways."""

    MAX_LINE_LENGTH: int = 4096

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.server: Optional[asyncio.AbstractServer] = None
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._current_conn_id: int = 0
        self._client_ready = asyncio.Event()
        self._write_lock = asyncio.Lock()
        self._read_lock = asyncio.Lock()
        self._closed: bool = False

    @property
    def current_conn_id(self) -> int:
        return self._current_conn_id

    async def open(self) -> None:
        self._closed = False
        if self.server is None:
            self.server = await asyncio.start_server(
                self._accept,
                self.host,
                self.port,
                limit=self.MAX_LINE_LENGTH,
            )
            if self.port == 0 and self.server.sockets:
                self.port = int(self.server.sockets[0].getsockname()[1])
            logger.info("Lander TCP transport listening on %s:%s", self.host, self.port)

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self._closed:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            return

        old_writer = self.writer
        old_reader = self.reader

        self._current_conn_id += 1
        conn_id = self._current_conn_id

        self.reader = reader
        self.writer = writer
        self._client_ready.set()

        # If a prior connection was open, terminate it cleanly so the new one takes over
        if old_writer is not None:
            try:
                old_writer.close()
                if hasattr(old_writer, "transport") and old_writer.transport is not None:
                    old_writer.transport.abort()
            except Exception:
                pass
        if old_reader is not None:
            old_reader.feed_eof()

        asyncio.create_task(self._monitor_connection(conn_id, writer), name=f"tcp_conn_monitor_{conn_id}")

    async def _monitor_connection(self, conn_id: int, writer: asyncio.StreamWriter) -> None:
        try:
            await writer.wait_closed()
        except Exception:
            pass
        finally:
            if self._current_conn_id == conn_id:
                self.reader = None
                self.writer = None
                self._client_ready.clear()

    async def disconnect_client(self, conn_id: Optional[int] = None) -> None:
        """Disconnect client. If conn_id is provided, only disconnects if it matches current connection."""
        if conn_id is not None and self._current_conn_id != conn_id:
            return

        writer = self.writer
        reader = self.reader
        self.reader = None
        self.writer = None
        self._client_ready.clear()
        if reader is not None:
            reader.feed_eof()
        if writer is not None:
            try:
                writer.close()
                if hasattr(writer, "transport") and writer.transport is not None:
                    writer.transport.abort()
                await writer.wait_closed()
            except Exception:
                pass

    async def close(self) -> None:
        self._closed = True
        await self.disconnect_client()
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

    def is_open(self) -> bool:
        if self._closed or self.writer is None or self.writer.is_closing():
            return False
        if self.reader is not None and self.reader.at_eof():
            return False
        return True

    async def read_line(self, timeout: Optional[float] = None) -> Optional[str]:
        """Read a line from the transport. Returns decoded string or None on timeout."""
        async with self._read_lock:
            if not self.is_open():
                try:
                    await asyncio.wait_for(self._client_ready.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    return None

            reader = self.reader
            if reader is None or reader.at_eof():
                raise ConnectionError("Lander Wi-Fi client disconnected (EOF)")

            try:
                raw = await asyncio.wait_for(reader.readline(), timeout=timeout)
            except asyncio.TimeoutError:
                return None
            except (ValueError, asyncio.LimitOverrunError) as exc:
                raise OversizedLineError(
                    f"Incoming line exceeds maximum buffer size of {self.MAX_LINE_LENGTH} bytes"
                ) from exc

            if not raw:
                raise ConnectionError("Lander Wi-Fi client disconnected (EOF)")

            if len(raw) > self.MAX_LINE_LENGTH:
                raise OversizedLineError(f"Incoming line exceeds limit ({len(raw)} > {self.MAX_LINE_LENGTH})")

            if not raw.endswith(b"\n"):
                raise ConnectionError("Incomplete line received before client disconnected")

            try:
                return raw.decode("utf-8").rstrip("\r\n")
            except UnicodeDecodeError as exc:
                raise InvalidEncodingError("Lander message must be valid UTF-8") from exc

    async def write_line(self, line: str) -> None:
        writer = self.writer
        if writer is None or writer.is_closing():
            raise ConnectionError("Lander Wi-Fi client is not connected")
        async with self._write_lock:
            writer.write((line.rstrip("\r\n") + "\n").encode("utf-8"))
            await writer.drain()
