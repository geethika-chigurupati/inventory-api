"""Redis cache that fails open: if Redis is down, requests fall back to the database."""
import json
import logging
from typing import Any

import redis

log = logging.getLogger("inventory.cache")

VERSION_KEY = "products:list:version"


class Cache:
    def __init__(self, client: redis.Redis, ttl_seconds: int = 60) -> None:
        self._client = client
        self._ttl = ttl_seconds

    def get_json(self, key: str) -> Any | None:
        try:
            raw = self._client.get(key)
        except redis.RedisError as exc:
            log.warning("cache read failed for %s: %s", key, exc)
            return None
        return json.loads(raw) if raw is not None else None

    def set_json(self, key: str, value: Any) -> None:
        try:
            self._client.set(key, json.dumps(value), ex=self._ttl)
        except redis.RedisError as exc:
            log.warning("cache write failed for %s: %s", key, exc)

    def delete(self, *keys: str) -> None:
        try:
            self._client.delete(*keys)
        except redis.RedisError as exc:
            log.warning("cache delete failed: %s", exc)

    def list_version(self) -> int:
        """List cache keys include this number; bumping it invalidates every cached list."""
        try:
            return int(self._client.get(VERSION_KEY) or 0)
        except redis.RedisError as exc:
            log.warning("cache version read failed: %s", exc)
            return 0

    def bump_list_version(self) -> None:
        try:
            self._client.incr(VERSION_KEY)
        except redis.RedisError as exc:
            log.warning("cache version bump failed: %s", exc)
