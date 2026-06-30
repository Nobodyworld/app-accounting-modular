"""OpenExchangeRates FX provider.

This provider expects an OpenExchangeRates App ID to be present in the
environment as ``OPENEXCHANGERATES_APP_ID``. The credential is never logged
and requests are made over HTTPS with conservative timeouts.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any

import requests
from apps.api.config import settings
from apps.api.models.models import Rate

logger = logging.getLogger(__name__)


class OpenExchangeRatesProvider:
    """Fetch FX rates from OpenExchangeRates."""

    name = "openexchangerates"

    def __init__(self, *, app_id: str | None = None, base_url: str = "https://openexchangerates.org/api"):
        self.app_id = (app_id or settings.openex_app_id or os.getenv("OPENEXCHANGERATES_APP_ID") or "").strip()
        if not self.app_id:
            raise ValueError("OpenExchangeRates app id is required (set OPENEXCHANGERATES_APP_ID)")
        self.base_url = base_url.rstrip("/")

    def _endpoint(self, base: str, date_: date | None) -> tuple[str, dict[str, Any]]:
        params = {"app_id": self.app_id}
        if base:
            params["base"] = base

        if date_ is None:
            path = "latest.json"
        else:
            path = f"historical/{date_.isoformat()}.json"
        return f"{self.base_url}/{path}", params

    def sync_daily_rates(self, base: str = "USD", date_: date | None = None) -> list[Rate]:
        url, params = self._endpoint(base, date_)
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()

        rates: list[Rate] = []
        body_base = payload.get("base", base)
        observed_raw = payload.get("date") or payload.get("timestamp")
        if observed_raw is None:
            observed_date = date_ or date.today()
        elif isinstance(observed_raw, (int, float)):
            observed_date = date.fromtimestamp(float(observed_raw))
        else:
            observed_date = date.fromisoformat(str(observed_raw))

        for quote, value in payload.get("rates", {}).items():
            rates.append(
                Rate(
                    base=str(body_base),
                    quote=str(quote),
                    date=observed_date,
                    value=float(value),
                    provider=self.name,
                )
            )
        logger.info(
            "Fetched %s FX rates from OpenExchangeRates",
            len(rates),
            extra={"provider": self.name, "base": body_base},
        )
        return rates


def provider() -> OpenExchangeRatesProvider:
    return OpenExchangeRatesProvider()
