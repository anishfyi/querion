"""Per-user daily question cap.

Each question can fan out to several model calls, so an unbounded surface can
run up cost. This is a small in-process daily counter keyed by whatever caller
identity you pass (a Slack user id, an authenticated username, an IP). State is
held in memory and optionally mirrored to a JSON file so it survives restarts.
"""

import datetime
import json
import os
import threading

_LOCK = threading.Lock()


class RateLimiter:
    def __init__(self, daily_limit: int = 50, state_path: str = ""):
        self.daily_limit = daily_limit
        self.state_path = state_path
        self._mem = {}
        if state_path:
            self._mem = self._load()

    @staticmethod
    def _today() -> str:
        return datetime.datetime.utcnow().strftime("%Y-%m-%d")

    def _load(self) -> dict:
        try:
            with open(self.state_path) as f:
                return json.load(f) or {}
        except (OSError, ValueError):
            return {}

    def _save(self):
        if not self.state_path:
            return
        try:
            os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
            tmp = self.state_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self._mem, f)
            os.replace(tmp, self.state_path)
        except OSError:
            pass

    def try_consume(self, key: str):
        """Count one question for `key` today. Returns (allowed, remaining).

        daily_limit <= 0 means unlimited.
        """
        if self.daily_limit <= 0:
            return True, -1
        key = key or "anon"
        today = self._today()
        with _LOCK:
            self._mem = {k: v for k, v in self._mem.items() if v.get("date") == today}
            rec = self._mem.get(key) or {"date": today, "count": 0}
            if rec["count"] >= self.daily_limit:
                self._mem[key] = rec
                self._save()
                return False, 0
            rec["count"] += 1
            self._mem[key] = rec
            self._save()
            return True, self.daily_limit - rec["count"]

    def reset_label(self) -> str:
        now = datetime.datetime.utcnow()
        nxt = (now + datetime.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0)
        mins = int((nxt - now).total_seconds() // 60)
        h, m = divmod(mins, 60)
        return f"in {h}h {m}m (00:00 UTC)" if h else f"in {m}m (00:00 UTC)"
