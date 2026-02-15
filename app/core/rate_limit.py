from collections import defaultdict
from time import time
from typing import Dict, List

import redis

from app.core.config import get_settings


class RateLimiter:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._memory_store: Dict[str, List[float]] = defaultdict(list)
        self._redis = None
        try:
            self._redis = redis.from_url(self.settings.redis_url, decode_responses=True)
            self._redis.ping()
        except Exception:
            self._redis = None

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        if self._redis:
            current = self._redis.incr(key)
            if current == 1:
                self._redis.expire(key, window_seconds)
            return current <= limit

        now = time()
        bucket = [ts for ts in self._memory_store[key] if now - ts <= window_seconds]
        bucket.append(now)
        self._memory_store[key] = bucket
        return len(bucket) <= limit


rate_limiter = RateLimiter()
