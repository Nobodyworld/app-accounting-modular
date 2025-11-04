"""First-party provider namespaces shipped with Modular Accounting.

The :mod:`plugins` package exposes the built-in integrations that ship with the
project (for example the European Central Bank FX provider or the OECD tax
stub).  At runtime the plugin loader dynamically imports the sub-packages based
on the configuration allow list, so keeping this namespace lightweight and
well-documented helps external contributors model their own extensions.
"""

__all__ = [
    "analytics_baseline",
    "fx_ecb",
    "market_yfinance",
    "ops_heartbeat",
    "scenario_variance",
    "tax_oecd_stub",
]
