import time
from threading import Lock
from typing import Any

from app.schemas.inventory import InventoryItem


class InventoryCache:
    """Thread-safe in-memory cache for inventory items with TTL."""

    def __init__(self, default_ttl_seconds: int = 60):
        self._default_ttl = default_ttl_seconds
        self._store: dict[str, dict[str, Any]] = {}
        self._lock = Lock()
        self.hits = 0
        self.misses = 0

    def _make_key(self, shop_id: str | None) -> str:
        return f"inventory:{shop_id or 'default'}"

    def get(self, shop_id: str | None = None) -> list[InventoryItem] | None:
        key = self._make_key(shop_id)
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if entry is not None:
                if entry["expires_at"] > now:
                    self.hits += 1
                    return entry["items"]
                else:
                    # Expired
                    del self._store[key]
            self.misses += 1
            return None

    def set(
        self,
        items: list[InventoryItem],
        shop_id: str | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        key = self._make_key(shop_id)
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        now = time.time()
        with self._lock:
            self._store[key] = {
                "items": items,
                "expires_at": now + ttl,
            }

    def invalidate(self, shop_id: str | None = None) -> None:
        with self._lock:
            if shop_id is not None:
                self._store.pop(self._make_key(shop_id), None)
            else:
                self._store.clear()

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self.hits = 0
            self.misses = 0


# Global singleton instance
inventory_cache = InventoryCache()
