"""Gateway Boundary Request ID Mapper.

Manages bidirectional mapping between MacBook UUID command_ids and
ESP32 32-bit integer request_ids at the gateway boundary.
"""

from __future__ import annotations

from collections import OrderedDict
from threading import Lock
from typing import Optional


class RequestIdMapper:
    """
    Thread-safe mapper for allocating and correlating integer request_ids
    (for ESP32 serial protocol) with UUID command_ids (for MacBook backend).
    """

    MAX_REQUEST_ID = 2_147_483_647  # int32_t positive range

    def __init__(self, max_history: int = 1000) -> None:
        self._lock = Lock()
        self._next_id: int = 1
        self._max_history = max_history

        # Bidirectional lookups
        self._uuid_to_int: dict[str, int] = {}
        self._int_to_uuid: dict[int, str] = {}

        # Retain history in insertion order for LRU eviction of completed mappings
        self._completed_history: OrderedDict[str, int] = OrderedDict()
        self._active_uuids: set[str] = set()

    def allocate(self, command_id: str) -> int:
        """
        Allocate a 32-bit integer request_id for a given UUID command_id.
        If the command_id already has an allocated request_id, returns it.
        """
        with self._lock:
            if command_id in self._uuid_to_int:
                return self._uuid_to_int[command_id]

            req_id = self._next_id
            self._next_id += 1
            if self._next_id > self.MAX_REQUEST_ID:
                self._next_id = 1  # Safe rollover

            self._uuid_to_int[command_id] = req_id
            self._int_to_uuid[req_id] = command_id
            self._active_uuids.add(command_id)

            return req_id

    def get_command_id(self, request_id: int) -> Optional[str]:
        """Look up the UUID command_id for an integer request_id."""
        with self._lock:
            return self._int_to_uuid.get(request_id)

    def get_request_id(self, command_id: str) -> Optional[int]:
        """Look up the integer request_id for a UUID command_id."""
        with self._lock:
            return self._uuid_to_int.get(command_id)

    def mark_completed(self, command_id: str) -> None:
        """
        Mark command as completed. It leaves active tracking and becomes
        eligible for bounded history eviction.
        """
        with self._lock:
            if command_id in self._active_uuids:
                self._active_uuids.remove(command_id)
                req_id = self._uuid_to_int.get(command_id)
                if req_id is not None:
                    self._completed_history[command_id] = req_id

            # Enforce history bound (evict oldest completed)
            while len(self._completed_history) > self._max_history:
                evicted_uuid, evicted_id = self._completed_history.popitem(last=False)
                self._uuid_to_int.pop(evicted_uuid, None)
                self._int_to_uuid.pop(evicted_id, None)

    def is_active(self, command_id: str) -> bool:
        """Check if command is currently active in the mapper."""
        with self._lock:
            return command_id in self._active_uuids

    def clear(self) -> None:
        """Reset all mappings (primarily for testing)."""
        with self._lock:
            self._next_id = 1
            self._uuid_to_int.clear()
            self._int_to_uuid.clear()
            self._completed_history.clear()
            self._active_uuids.clear()
