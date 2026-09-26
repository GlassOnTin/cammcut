"""Thread-safe event buffer for SSE.

Job progress is published from the worker thread while SSE generators read
from the event loop, so this is a plain locked ring buffer that consumers
poll — no cross-thread asyncio plumbing. Events older than the buffer are
lost, which is fine: every message carries full state, not a delta.
"""

import json
import threading
from collections import deque
from typing import Any

MAX_EVENTS = 1000


class Broadcaster:
    def __init__(self):
        self._lock = threading.Lock()
        self._events: deque[tuple[int, str]] = deque(maxlen=MAX_EVENTS)
        self._next = 0

    def publish(self, event_type: str, data: dict[str, Any]):
        msg = json.dumps({"type": event_type, **data})
        with self._lock:
            self._events.append((self._next, msg))
            self._next += 1

    def cursor(self) -> int:
        """Read everything published before now."""
        with self._lock:
            return self._next

    def since(self, idx: int) -> list[tuple[int, str]]:
        with self._lock:
            return [e for e in self._events if e[0] >= idx]