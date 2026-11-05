"""Small, bounded, thread-safe in-memory record engine."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import json
import re
from threading import RLock
import time
from typing import Any


@dataclass(frozen=True)
class Record:
    id: int
    timestamp: float
    tag: str
    data: dict


class CoreEngine:
    """Store the newest ``capacity`` records and index them by tag."""

    def __init__(self, capacity: int = 100000) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValueError("capacity must be a positive integer")
        self.capacity = capacity
        self._records: deque[Record] = deque()
        self._by_tag: dict[str, deque[Record]] = defaultdict(deque)
        self._next_id = 1
        self._lock = RLock()

    def append(self, tag: str, data: dict) -> Record:
        """Append a record, evicting the oldest record when full."""
        if not isinstance(tag, str):
            raise TypeError("tag must be a string")
        if not isinstance(data, dict):
            raise TypeError("data must be a dict")
        with self._lock:
            record = Record(self._next_id, time.time(), tag, data)
            self._next_id += 1
            if len(self._records) == self.capacity:
                oldest = self._records.popleft()
                tagged = self._by_tag[oldest.tag]
                tagged.popleft()
                if not tagged:
                    del self._by_tag[oldest.tag]
            self._records.append(record)
            self._by_tag[tag].append(record)
            return record

    def query_by_tag(self, tag: str) -> list[Record]:
        """Return retained records with ``tag``, in insertion order."""
        with self._lock:
            return list(self._by_tag.get(tag, ()))

    def query_regex(self, pattern: str) -> list[Record]:
        """Return records whose tag matches the regular expression."""
        compiled = re.compile(pattern)
        with self._lock:
            return [record for record in self._records if compiled.search(record.tag)]

    def get_stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "count": len(self._records),
                "capacity": self.capacity,
                "tags": len(self._by_tag),
            }

    def process(self, action: str, payload_json: str) -> str:
        """Dispatch an action using a JSON object payload; return JSON output.

        ``append`` expects ``{"tag": ..., "data": ...}``; queries expect
        ``{"tag": ...}`` or ``{"pattern": ...}``; ``get_stats`` ignores
        its payload. Record dictionaries contain ``id``, ``timestamp``,
        ``tag`` and ``data`` fields.
        """
        payload: Any = json.loads(payload_json)
        if not isinstance(payload, dict):
            raise ValueError("payload_json must encode a JSON object")
        if action == "append":
            result: Any = self.append(payload["tag"], payload["data"])
        elif action == "query_by_tag":
            result = self.query_by_tag(payload["tag"])
        elif action == "query_regex":
            result = self.query_regex(payload["pattern"])
        elif action == "get_stats":
            result = self.get_stats()
        else:
            raise ValueError(f"unknown action: {action}")

        def encode(value: Any) -> Any:
            if isinstance(value, Record):
                return {"id": value.id, "timestamp": value.timestamp,
                        "tag": value.tag, "data": value.data}
            if isinstance(value, list):
                return [encode(item) for item in value]
            return value

        return json.dumps(encode(result), separators=(",", ":"))
