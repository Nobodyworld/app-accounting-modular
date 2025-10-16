from datetime import date
from typing import List
import yfinance as yf
from apps.api.models.models import Price

class YFinanceProvider:
    name = "yfinance"

    def fetch_prices(self, symbol: str, start: date, end: date) -> List[Price]:
        df = yf.download(symbol, start=start.isoformat(), end=end.isoformat(), progress=False, auto_adjust=False)
        prices = []
        if df is None or df.empty:
            return prices
        for idx, row in df.iterrows():
            prices.append(Price(instrument_id=0, date=idx.date(), close=float(row["Close"]), provider=self.name))
        return prices

def provider():
    return YFinanceProvider()
