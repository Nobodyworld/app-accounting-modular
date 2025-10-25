"""Lightweight caching utilities for snapshot orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Generic, Protocol, TypeVar

__all__ = ["CacheEntry", "CacheObserver", "CacheStats", "TTLCache"]

K = TypeVar("K")
V = TypeVar("V")


@dataclass(slots=True)
class CacheEntry(Generic[V]):
    """Container storing cached values with optional expiry metadata."""

    value: V
    expires_at: float | None

    def is_expired(self, *, now: float | None = None) -> bool:
        """Return ``True`` when the entry has expired."""

        if self.expires_at is None:
            return False
        current = monotonic() if now is None else now
        return current >= self.expires_at


@dataclass(slots=True, frozen=True)
class CacheStats:
    """Snapshot of cache usage metrics."""

    size: int
    hits: int
    misses: int


class CacheObserver(Protocol):
    """Interface for receiving cache instrumentation callbacks."""

    def record_hit(self) -> None:  # pragma: no cover - simple delegation
        """Record that a cache lookup resulted in a hit."""

    def record_miss(self) -> None:  # pragma: no cover - simple delegation
        """Record that a cache lookup resulted in a miss."""

    def record_size(self, size: int) -> None:  # pragma: no cover - simple delegation
        """Record the current size of the cache."""


class TTLCache(Generic[K, V]):
    """Thread-safe cache with optional time-to-live semantics."""

    def __init__(
        self,
        *,
        default_ttl: float | None = None,
        clock: Callable[[], float] | None = None,
        observer: CacheObserver | None = None,
    ) -> None:
        if default_ttl is not None and default_ttl <= 0:
            raise ValueError("default_ttl must be greater than zero when provided")
        self._default_ttl = default_ttl
        self._clock = clock or monotonic
        self._lock = RLock()
        self._entries: dict[K, CacheEntry[V]] = {}
        self._hits = 0
        self._misses = 0
        self._observer = observer

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: K) -> V | None:
        """Return a cached value if present and not expired."""

        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                if self._observer is not None:
                    self._observer.record_miss()
                return None
            if entry.is_expired(now=self._clock()):
                self._entries.pop(key, None)
                self._misses += 1
                if self._observer is not None:
                    self._observer.record_miss()
                    self._observer.record_size(len(self._entries))
                return None
            self._hits += 1
            if self._observer is not None:
                self._observer.record_hit()
            return entry.value

    def set(self, key: K, value: V, *, ttl: float | None = None) -> None:
        """Store ``value`` under ``key`` with an optional custom TTL."""

        expiry = self._expiry(ttl)
        with self._lock:
            self._entries[key] = CacheEntry(value=value, expires_at=expiry)
            if self._observer is not None:
                self._observer.record_size(len(self._entries))

    def get_or_set(
        self,
        key: K,
        factory: Callable[[], V],
        *,
        ttl: float | None = None,
    ) -> V:
        """Return a cached value or compute and store it lazily."""

        cached = self.get(key)
        if cached is not None:
            return cached

        value = factory()
        self.set(key, value, ttl=ttl)
        return value

    def invalidate(self, key: K | None = None) -> None:
        """Remove cached entries for ``key`` or clear the entire cache."""

        with self._lock:
            if key is None:
                self._entries.clear()
            else:
                self._entries.pop(key, None)
            if self._observer is not None:
                self._observer.record_size(len(self._entries))

    def stats(self) -> CacheStats:
        """Return usage metrics for observability and testing."""

        with self._lock:
            return CacheStats(
                size=len(self._entries), hits=self._hits, misses=self._misses
            )

    def _expiry(self, ttl: float | None) -> float | None:
        effective_ttl = ttl if ttl is not None else self._default_ttl
        if effective_ttl is None:
            return None
        if effective_ttl <= 0:
            raise ValueError("TTL must be greater than zero")
        return self._clock() + effective_ttl
