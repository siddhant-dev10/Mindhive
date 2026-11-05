"""
Core Engine Module for AgentHive Project.
Authored by ChatGPT Codex under Pony Tail Minimalism Rules.
"""

from dataclasses import dataclass
from collections import deque, defaultdict
from typing import List, Dict, Any, Generator
import time
import threading
import re


@dataclass(frozen=True)
class Record:
    id: int
    timestamp: float
    tag: str
    data: Dict[str, Any]


class CoreEngine:
    def __init__(self, capacity: int = 100_000):
        self.capacity = capacity
        self._buffer: deque[Record] = deque(maxlen=capacity)
        self._tag_index: Dict[str, List[int]] = defaultdict(list)
        self._counter: int = 0
        self._lock = threading.RLock()

    def append(self, tag: str, data: Dict[str, Any]) -> Record:
        with self._lock:
            self._counter += 1
            record = Record(
                id=self._counter,
                timestamp=time.time(),
                tag=tag,
                data=data
            )
            self._buffer.append(record)
            self._tag_index[tag].append(record.id)
            return record

    def query_by_tag(self, tag: str) -> List[Record]:
        with self._lock:
            return [r for r in self._buffer if r.tag == tag]

    def query_regex(self, pattern: str) -> Generator[Record, None, None]:
        compiled = re.compile(pattern)
        with self._lock:
            for record in self._buffer:
                if compiled.search(record.tag) or any(compiled.search(str(v)) for v in record.data.values()):
                    yield record

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'total_ingested': self._counter,
                'active_records': len(self._buffer),
                'capacity': self.capacity,
                'unique_tags': len(self._tag_index)
            }

    def process(self, action: str, payload_json: str) -> Dict[str, Any]:
        """CLI Dispatcher Entrypoint."""
        if action == 'status':
            return self.get_stats()
        elif action == 'run':
            rec = self.append('audit', {'payload': payload_json})
            return {'status': 'success', 'record_id': rec.id, 'stats': self.get_stats()}
        return {'status': 'unknown_action', 'action': action}
