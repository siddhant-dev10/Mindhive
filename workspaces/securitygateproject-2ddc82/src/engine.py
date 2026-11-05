"""Thread-safe, bounded in-memory record engine."""

from collections import deque
from dataclasses import dataclass
import re
import threading
import time
from typing import Any


@dataclass(frozen=True)
class Record:
    id: int
    timestamp: float
    tag: str
    data: dict


class CoreEngine:
    """Store the newest ``capacity`` records and support indexed tag queries."""

    def __init__(self, capacity: int = 100_000):
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
            raise ValueError("capacity must be a positive integer")
        self.capacity = capacity
        self._buffer: deque[Record] = deque()
        self._tag_index: dict[str, deque[Record]] = {}
        self._counter = 0
        self._lock = threading.RLock()

    def append(self, tag: str, data: dict) -> Record:
        """Append a record, evicting the oldest record when the buffer is full."""
        if not isinstance(tag, str):
            raise TypeError("tag must be a string")
        if not isinstance(data, dict):
            raise TypeError("data must be a dict")

        with self._lock:
            record = Record(self._counter + 1, time.time(), tag, data)
            if len(self._buffer) == self.capacity:
                oldest = self._buffer.popleft()
                bucket = self._tag_index[oldest.tag]
                bucket.popleft()
                if not bucket:
                    del self._tag_index[oldest.tag]
            self._buffer.append(record)
            self._tag_index.setdefault(tag, deque()).append(record)
            self._counter = record.id
            return record

    def query_by_tag(self, tag: str) -> list[Record]:
        """Return matching live records in append order."""
        with self._lock:
            return list(self._tag_index.get(tag, ()))

    def query_regex(self, pattern: str) -> list[Record]:
        """Return records whose tag or top-level data value matches a regex."""
        compiled = re.compile(pattern)
        with self._lock:
            records = tuple(self._buffer)
        return [
            record
            for record in records
            if compiled.search(record.tag)
            or any(compiled.search(str(value)) for value in record.data.values())
        ]

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_ingested": self._counter,
                "active_records": len(self._buffer),
                "capacity": self.capacity,
                "unique_tags": len(self._tag_index),
            }

    def process(self, action: str, payload_json: str) -> dict[str, Any]:
        """Dispatch the small JSON-facing interface used by the CLI."""
        if action == "status":
            return self.get_stats()
        if action == "run":
            record = self.append("audit", {"payload": payload_json})
            return {
                "status": "success",
                "record_id": record.id,
                "stats": self.get_stats(),
            }
        return {"status": "unknown_action", "action": action}
