import math
import re
from collections.abc import Mapping
from datetime import date

from apps.api.models.models import Rate

from plugins.provider_limits import (
    MAX_FX_RATE_RECORDS,
    ProviderPayloadError,
    ProviderResponseLimitError,
    get_bounded_json,
)

_CURRENCY_CODE = re.compile(r"^[A-Z]{3}$")


# ECB reference rates are fetched through the shared bounded, two-attempt HTTPS policy.
class ECBFXProvider:
    name = "ecb_reference_via_exchangerate_host"

    def sync_daily_rates(self, base: str = "USD", date_: date | None = None) -> list[Rate]:
        endpoint = (
            "https://api.exchangerate.host/latest"
            if date_ is None
            else f"https://api.exchangerate.host/{date_.isoformat()}"
        )
        data = get_bounded_json(
            endpoint,
            params={"base": base},
            provider_key=self.name,
            operation="sync-daily-rates",
        )
        raw_date = data.get("date")
        try:
            if isinstance(raw_date, str) and raw_date.strip():
                observed_date = date.fromisoformat(raw_date)
            elif date_ is not None:
                observed_date = date_
            else:
                observed_date = date.today()
        except ValueError as exc:
            raise ProviderPayloadError("Provider returned an invalid payload") from exc

        raw_rates = data.get("rates")
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
                    base=base,
                    quote=quote,
                    date=observed_date,
                    value=value,
                    provider=self.name,
                )
            )
        return rates


def provider() -> ECBFXProvider:
    return ECBFXProvider()
