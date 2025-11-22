"""First-party provider namespaces shipped with Modular Accounting.

The :mod:`plugins` package exposes the built-in integrations that ship with the
project (for example the European Central Bank FX provider or the OECD tax
stub).  At runtime the plugin loader dynamically imports the sub-packages based
on the configuration allow list, so keeping this namespace lightweight and
well-documented helps external contributors model their own extensions.
"""

__all__ = [
    "analytics_baseline",
    "bank_plaid",
    "fx_ecb",
    "fx_openexchangerates",
    "macro_fred",
    "market_commodities",
    "market_yfinance",
    "ops_heartbeat",
    "scenario_variance",
    "tax_oecd_vat",
    "tax_oecd_stub",
    "tax_us_tables",
]

# Expose plugin subpackages for static analyzers and discoverability.
from . import (  # noqa: E402,F401
    analytics_baseline,
    bank_plaid,
    fx_ecb,
    fx_openexchangerates,
    macro_fred,
    market_commodities,
    market_yfinance,
    ops_heartbeat,
    ops_resilience,
    reference_cashflow,
    scenario_variance,
    tax_oecd_vat,
    tax_oecd_stub,
    tax_us_tables,
)

# Avoid linter noise for plugins not listed in __all__ but available.
__all__ = [
    "analytics_baseline",
    "bank_plaid",
    "fx_ecb",
    "fx_openexchangerates",
    "macro_fred",
    "market_commodities",
    "market_yfinance",
    "ops_heartbeat",
    "scenario_variance",
    "tax_oecd_vat",
    "tax_oecd_stub",
    "tax_us_tables",
]
