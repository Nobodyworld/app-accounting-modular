from __future__ import annotations

from apps.api.dependencies import _spoofed_header_counter, _trusted_request_id
from apps.observability.metrics import metrics_registry


def test_malformed_request_id_metrics_increment() -> None:
    before = metrics_registry.render_latest().decode()
    resolved = _trusted_request_id("not a valid request id")
    after = metrics_registry.render_latest().decode()

    assert resolved != "not a valid request id"
    assert after != before
    assert "modacct_header_malformed_total" in after
    assert 'header="request-id"' in after


def test_spoofed_header_metrics_increment() -> None:
    _spoofed_header_counter.labels(reason="client-identity-header").inc()
    after = metrics_registry.render_latest().decode()

    assert "modacct_header_spoof_total" in after
    assert 'reason="client-identity-header"' in after
