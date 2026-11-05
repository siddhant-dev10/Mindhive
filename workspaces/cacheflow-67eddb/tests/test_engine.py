"""
Automated Adversarial Test Matrix for AgentHive Project.
Authored by Google Gemini (Independent QA Specialist).
"""

import unittest
import threading
import time
from src.engine import CoreEngine, Record


class TestCoreEngine(unittest.TestCase):
    def setUp(self):
        self.engine = CoreEngine(capacity=5)

    def test_basic_append_and_stats(self):
        rec = self.engine.append('user', {'action': 'login'})
        self.assertEqual(rec.id, 1)
        self.assertEqual(rec.tag, 'user')
        stats = self.engine.get_stats()
        self.assertEqual(stats['total_ingested'], 1)
        self.assertEqual(stats['active_records'], 1)

    def test_ring_buffer_capacity_eviction(self):
        # Append 7 items into capacity=5 ring buffer
        for i in range(1, 8):
            self.engine.append('event', {'val': i})
        stats = self.engine.get_stats()
        self.assertEqual(stats['total_ingested'], 7)
        self.assertEqual(stats['active_records'], 5)
        # Oldest records (1, 2) should have been evicted; remaining are 3..7
        active_tags = self.engine.query_by_tag('event')
        self.assertEqual(len(active_tags), 5)
        self.assertEqual(active_tags[0].id, 3)
        self.assertEqual(active_tags[-1].id, 7)

    def test_query_regex(self):
        self.engine.append('metrics', {'cpu': '95%', 'host': 'node-1'})
        self.engine.append('audit', {'status': 'success'})
        results = list(self.engine.query_regex(r'node-\d+'))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tag, 'metrics')

    def test_concurrent_multithreaded_writes(self):
        """Verify thread safety under 20 concurrent threads writing 10 records each."""
        def worker(thread_idx):
            for j in range(10):
                self.engine.append(f'thread-{thread_idx}', {'seq': j})

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stats = self.engine.get_stats()
        self.assertEqual(stats['total_ingested'], 200)
        self.assertEqual(stats['active_records'], 5)


if __name__ == '__main__':
    unittest.main()
