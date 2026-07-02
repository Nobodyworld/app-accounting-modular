# Scripts

This directory is reserved for development and operations helper scripts. The
primary automation entry points currently live in the root `Makefile` and under
`src/tools/`.

## Common Commands

Run these from the repository root after installing development dependencies:

```bash
make install
make quality-gate
make audit
make health
```

The canonical release gate is:

```bash
python -m src.tools.quality_gate
```

## Release Evidence

Release status and publication evidence are tracked in
`PUBLIC_RELEASE_AUDIT.md`, including clean-clone validation, hosted CI
disposition, and secret-scanning evidence for the audited release candidate.

## License

This project is licensed under the Apache License 2.0. See `LICENSE` and
`NOTICE` at the repository root.
