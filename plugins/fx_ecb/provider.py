"""European Central Bank FX provider implementation."""

from __future__ import annotations

from datetime import date
from typing import Iterable

import requests

from apps.api.models.models import Rate

API_ROOT = "https://api.exchangerate.host"

__all__ = ["ECBFXProvider", "provider"]


class ECBFXProvider:
    """Fetch FX rates using the exchangerate.host ECB mirror."""

    name = "ecb_reference_via_exchangerate_host"

    def sync_daily_rates(self, base: str = "USD", date_: date | None = None) -> Iterable[Rate]:
        endpoint = f"{API_ROOT}/latest?base={base}" if date_ is None else f"{API_ROOT}/{date_.isoformat()}?base={base}"
        response = requests.get(endpoint, timeout=20)
        response.raise_for_status()
        payload = response.json()
        rate_date = date.fromisoformat(payload["date"])
        for quote, value in payload.get("rates", {}).items():
            yield Rate(
                base=base,
                quote=quote,
                date=rate_date,
                value=float(value),
                provider=self.name,
            )


def provider() -> ECBFXProvider:
    """Entry point for the plugin loader."""

    return ECBFXProvider()
