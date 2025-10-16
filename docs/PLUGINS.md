# Plugins

Drop a folder under `plugins/` that exposes a provider module with a `provider()` factory returning an instance of your provider implementation.

Example layout:

```bash
plugins/
  fx_ecb/
    __init__.py
    provider.py
```

Your `provider()` should return an object implementing the desired contract (FX, Market, Tax). The loader will import `plugins.<name>.provider:provider` and register it.

## Example: FX (ECB)

See `plugins/fx_ecb/provider.py` for a working example using ECB reference rates.
