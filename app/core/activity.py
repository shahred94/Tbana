"""Thread-safe recent activity feed for the local dashboard."""

from collections import deque
from datetime import datetime, timezone
import threading


class ActivityFeed:
    def __init__(self, limit: int = 100):
        self.items = deque(maxlen=limit)
        self.lock = threading.RLock()
        self.next_id = 1

    def record(
        self,
        activity_type: str,
        status: str,
        title: str,
        detail: str = "",
        user: str = "",
    ) -> dict:
        with self.lock:
            item = {
                "id": self.next_id,
                "timestamp": datetime.now(
                    timezone.utc
                ).isoformat(),
                "type": activity_type,
                "status": status,
                "title": title,
                "detail": detail,
                "user": user,
            }
            self.next_id += 1
            self.items.appendleft(item)
            return item

    def recent(self, limit: int = 30) -> list[dict]:
        safe_limit = min(100, max(1, int(limit)))
        with self.lock:
            return list(self.items)[:safe_limit]

    def clear(self) -> None:
        with self.lock:
            self.items.clear()


activity_feed = ActivityFeed()
