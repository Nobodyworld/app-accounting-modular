from datetime import date

import requests
from apps.api.models.models import Rate


# Simple ECB reference rates via exchangerate.host (free mirror) to avoid API keys.
# NOTE: For production, pin a compliant source and add retries/caching.
class ECBFXProvider:
    name = "ecb_reference_via_exchangerate_host"

    def sync_daily_rates(self, base: str = "USD", date_: date | None = None) -> list[Rate]:
        # if date_ is None, latest
        endpoint = (
            f"https://api.exchangerate.host/latest?base={base}"
            if date_ is None
            else f"https://api.exchangerate.host/{date_.isoformat()}?base={base}"
        )
        r = requests.get(endpoint, timeout=20)
        r.raise_for_status()
        data = r.json()
        d = date.fromisoformat(data["date"])
        out = []
        for quote, val in data.get("rates", {}).items():
            out.append(Rate(base=base, quote=quote, date=d, value=float(val), provider=self.name))
        return out


def provider():
    return ECBFXProvider()
