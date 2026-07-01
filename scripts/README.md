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

Public release remains `KEEP PRIVATE - NEAR READY` until
`PUBLIC_RELEASE_AUDIT.md` records full-history secret scanning, final
clean-clone validation, and hosted CI disposition for the publication commit.

## License

This project is licensed under the Apache License 2.0. See `LICENSE` and
`NOTICE` at the repository root.
