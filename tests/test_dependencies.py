from __future__ import annotations

from apps.api.dependencies import _parse_optional_int
from apps.observability.metrics import metrics_registry


def test_malformed_header_metrics_increment() -> None:
    before = metrics_registry.render_latest().decode()
    _parse_optional_int("abc")
    after = metrics_registry.render_latest().decode()
    assert after != before
    assert "modacct_header_malformed_total" in after
    assert 'header="id"' in after


def test_spoofed_header_metrics_increment() -> None:
    from apps.api.dependencies import _spoofed_header_counter

    before = metrics_registry.render_latest().decode()
    _spoofed_header_counter.labels(reason="missing-org").inc()
    after = metrics_registry.render_latest().decode()
    assert "modacct_header_spoof_total" in after
