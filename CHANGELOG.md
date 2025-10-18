# Changelog

## Unreleased

- 2025-10-18: Use timezone-aware UTC datetimes across the codebase for audit, workflow, budget, and security timestamps. This reduces deprecation warnings from third-party libraries and ensures JWT expiries and serialized timestamps include timezone info.
