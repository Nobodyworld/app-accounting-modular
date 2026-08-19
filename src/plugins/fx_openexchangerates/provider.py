"""OpenExchangeRates FX provider.

This provider expects an OpenExchangeRates App ID to be present in the
environment as ``OPENEXCHANGERATES_APP_ID``. The credential is never logged
and requests are made over HTTPS with conservative timeouts.
"""

from __future__ import annotations

import logging
import math
import os
import re
from collections.abc import Mapping
from datetime import date

from apps.api.config import settings
from apps.api.models.models import Rate
from apps.provider_sdk import ProviderManifest

from plugins.provider_limits import (
    MAX_FX_RATE_RECORDS,
    ProviderPayloadError,
    ProviderResponseLimitError,
    get_bounded_json,
)

__version__ = "0.3.0"

PROVIDER_MANIFEST = ProviderManifest(
    key="fx:openexchangerates",
    name="OpenExchangeRates FX",
    version=__version__,
    api_major=0,
    capabilities=("fx",),
    description="Credentialed bounded HTTPS adapter for OpenExchangeRates.",
    license="Apache-2.0",
    network_policy="https",
    credential_env=("OPENEXCHANGERATES_APP_ID",),
    data_classification="external-service",
)

logger = logging.getLogger(__name__)
_CURRENCY_CODE = re.compile(r"^[A-Z]{3}$")


class OpenExchangeRatesProvider:
    """Fetch FX rates from OpenExchangeRates."""

    name = "openexchangerates"

    def __init__(self, *, app_id: str | None = None, base_url: str = "https://openexchangerates.org/api"):
        self.app_id = (app_id or settings.openex_app_id or os.getenv("OPENEXCHANGERATES_APP_ID") or "").strip()
        if not self.app_id:
            raise ValueError("OpenExchangeRates app id is required (set OPENEXCHANGERATES_APP_ID)")
        self.base_url = base_url.rstrip("/")

    def _endpoint(self, base: str, date_: date | None) -> tuple[str, dict[str, str]]:
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
        payload = get_bounded_json(
            url,
            params=params,
            provider_key=self.name,
            operation="sync-daily-rates",
        )

        body_base = payload.get("base", base)
        observed_raw = payload.get("date") or payload.get("timestamp")
        try:
            if observed_raw is None:
                observed_date = date_ or date.today()
            elif isinstance(observed_raw, (int, float)) and not isinstance(observed_raw, bool):
                observed_date = date.fromtimestamp(float(observed_raw))
            elif isinstance(observed_raw, str):
                observed_date = date.fromisoformat(observed_raw)
            else:
                raise ValueError
        except (OSError, OverflowError, ValueError) as exc:
            raise ProviderPayloadError("Provider returned an invalid payload") from exc

        if not isinstance(body_base, str) or not _CURRENCY_CODE.fullmatch(body_base):
            raise ProviderPayloadError("Provider returned an invalid payload")
        raw_rates = payload.get("rates")
        if not isinstance(raw_rates, Mapping):
            raise ProviderPayloadError("Provider returned an invalid payload")
        if len(raw_rates) > MAX_FX_RATE_RECORDS:
            raise ProviderResponseLimitError("Provider response exceeded the configured limit")

        rates: list[Rate] = []
        for quote, raw_value in raw_rates.items():
            if not isinstance(quote, str) or not _CURRENCY_CODE.fullmatch(quote):
                raise ProviderPayloadError("Provider returned an invalid payload")
            try:
                value = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise ProviderPayloadError("Provider returned an invalid payload") from exc
            if isinstance(raw_value, bool) or not math.isfinite(value) or value <= 0:
                raise ProviderPayloadError("Provider returned an invalid payload")
            rates.append(
                Rate(
                    base=body_base,
                    quote=quote,
                    date=observed_date,
                    value=value,
                    provider=self.name,
                )
            )
        logger.info(
            "Fetched %s FX rates from outbound provider",
            len(rates),
            extra={"provider": self.name, "operation": "sync-daily-rates"},
        )
        return rates


def provider() -> OpenExchangeRatesProvider:
    return OpenExchangeRatesProvider()
