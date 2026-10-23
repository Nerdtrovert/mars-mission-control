"""Serial Transport Abstraction for Hardware Gateway.

Provides abstract interface and concrete implementations:
- PySerialTransport: Connects to physical USB serial hardware.
- SimulatedSerialTransport: In-memory queues for deterministic, hardware-free testing.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Optional
import anyio


class SerialTransport(ABC):
    """Abstract interface for serial communication with the ESP32 lander."""

    @abstractmethod
    async def open(self) -> None:
        """Open the serial port transport."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the serial port transport."""
        pass

    @abstractmethod
    def is_open(self) -> bool:
        """Check whether the transport is currently open."""
        pass

    @abstractmethod
    async def read_line(self, timeout: Optional[float] = None) -> Optional[str]:
        """Read a single newline-delimited line from the transport."""
        pass

    @abstractmethod
    async def write_line(self, line: str) -> None:
        """Write a single newline-delimited line to the transport."""
        pass


class PySerialTransport(SerialTransport):
    """Physical serial transport using pyserial."""

    def __init__(self, port: str, baud_rate: int = 115200) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self._serial = None

    async def open(self) -> None:
        import serial

        def _open_sync():
            return serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.5,
                write_timeout=1.0,
            )

        self._serial = await anyio.to_thread.run_sync(_open_sync)

    async def close(self) -> None:
        if self._serial is not None and self._serial.is_open:
            def _close_sync():
                self._serial.close()
            await anyio.to_thread.run_sync(_close_sync)
        self._serial = None

    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    async def read_line(self, timeout: Optional[float] = None) -> Optional[str]:
        if not self.is_open():
            raise ConnectionError("Serial port is not open")

        def _readline_sync() -> Optional[str]:
            raw = self._serial.readline()
            if not raw:
                return None
            return raw.decode("utf-8", errors="replace").rstrip("\r\n")

        return await anyio.to_thread.run_sync(_readline_sync)

    async def write_line(self, line: str) -> None:
        if not self.is_open():
            raise ConnectionError("Serial port is not open")

        encoded = (line.rstrip("\r\n") + "\n").encode("utf-8")

        def _write_sync():
            self._serial.write(encoded)
            self._serial.flush()

        await anyio.to_thread.run_sync(_write_sync)


import queue


class SimulatedSerialTransport(SerialTransport):
    """
    Thread-safe in-memory simulated serial transport for deterministic, hardware-free testing.
    Supports cross-thread communication between test runner and gateway daemon.
    """

    def __init__(self) -> None:
        self.rx_queue: queue.Queue[str] = queue.Queue()
        self.tx_queue: queue.Queue[str] = queue.Queue()
        self._is_open: bool = False
        self._connected: bool = True

    async def open(self) -> None:
        if not self._connected:
            raise ConnectionError("Simulated serial port unplugged")
        self._is_open = True

    async def close(self) -> None:
        self._is_open = False

    def is_open(self) -> bool:
        return self._is_open and self._connected

    def disconnect(self) -> None:
        """Simulate unplugging the USB cable."""
        self._connected = False
        self._is_open = False

    def reconnect(self) -> None:
        """Simulate re-plugging the USB cable."""
        self._connected = True

    def inject_rx_line(self, line: str) -> None:
        """Simulate a line sent from the ESP32 to the gateway."""
        self.rx_queue.put(line.rstrip("\r\n"))

    async def get_tx_line(self, timeout: Optional[float] = 1.0) -> str:
        """Retrieve a line sent by the gateway to the ESP32."""
        def _get():
            return self.tx_queue.get(timeout=timeout)

        try:
            return await asyncio.to_thread(_get)
        except queue.Empty:
            raise asyncio.TimeoutError()

    async def read_line(self, timeout: Optional[float] = None) -> Optional[str]:
        if not self.is_open():
            raise ConnectionError("Simulated serial port is disconnected")

        def _read():
            try:
                return self.rx_queue.get(timeout=timeout or 0.05)
            except queue.Empty:
                return None

        return await asyncio.to_thread(_read)

    async def write_line(self, line: str) -> None:
        if not self.is_open():
            raise ConnectionError("Simulated serial port is disconnected")

        self.tx_queue.put(line.rstrip("\r\n"))
