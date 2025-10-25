from __future__ import annotations

from apps.modular_accounting.application.cache import TTLCache
from apps.observability.metrics import CacheMetricsObserver, MetricsRegistry


def test_cache_metrics_observer_tracks_hits_and_misses() -> None:
    registry = MetricsRegistry.create()
    observer = CacheMetricsObserver(registry=registry, cache_name="unit-test")
    cache: TTLCache[str, int] = TTLCache(observer=observer)

    cache.set("answer", 42)
    assert cache.get("answer") == 42
    assert cache.get("missing") is None

    metrics = registry.render_latest().decode()
    assert 'modacct_cache_entries{cache="unit-test"} 1' in metrics
    assert 'modacct_cache_hits_total{cache="unit-test"} 1.0' in metrics
    assert 'modacct_cache_misses_total{cache="unit-test"} 1.0' in metrics
