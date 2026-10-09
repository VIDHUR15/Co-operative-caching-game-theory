"""
cache_store.py

A standalone, real LRU cache for one edge node process.

Same eviction policy as topology.py's add_to_cache()/
touch_cache() (true least-recently-used, not the arbitrary
set.pop() bug from earlier in this project) - but decoupled
from the simulation's networkx graph, since a live edge node
is a real standalone process, not a node in a simulated
network.
"""

import threading
import time
from collections import OrderedDict


class LRUCache:
    """
    Thread-safe real LRU cache, keyed by article title.

    Stores actual content bytes/text, real sizes, and real
    fetch timestamps - this is genuinely caching real data in
    memory, not tracking a boolean "is this cached" flag like
    the simulation does.
    """

    def __init__(self, capacity):
        self.capacity = capacity
        self._store = OrderedDict()
        self._lock = threading.Lock()

        # Real cumulative stats, updated as real requests are
        # actually served.
        self.local_hits = 0
        self.cooperative_hits = 0
        self.origin_requests = 0

    def get(self, key):
        """
        Returns (content, size_mb) if cached, else None.
        Marks the item as recently used on a hit, exactly
        like touch_cache() does in the simulation.
        """

        with self._lock:
            if key not in self._store:
                return None

            self._store.move_to_end(key)
            return self._store[key]

    def put(self, key, content, size_mb):
        """
        Adds an item to the cache, evicting the real
        least-recently-used item if the cache is full.
        """

        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
                self._store[key] = (content, size_mb)
                return

            if len(self._store) >= self.capacity:
                self._store.popitem(last=False)

            self._store[key] = (content, size_mb)

    def contains(self, key):
        with self._lock:
            return key in self._store

    def snapshot(self):
        """Real current cache contents, most-recent last."""
        with self._lock:
            return list(self._store.keys())

    def __len__(self):
        with self._lock:
            return len(self._store)
