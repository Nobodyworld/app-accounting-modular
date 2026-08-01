#!/usr/bin/env sh
set -eu

repository_root="$(git rev-parse --show-toplevel)"
base_image="python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6"

docker run --rm \
  --platform linux/amd64 \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=${repository_root},target=/workspace" \
  --workdir /workspace \
  --env HOME=/tmp/modacct-lock-home \
  --env UV_CACHE_DIR=/tmp/modacct-uv-cache \
  "${base_image}" \
  sh -euc '
    python -m venv /tmp/modacct-lock-tools
    /tmp/modacct-lock-tools/bin/python -m pip install \
      --disable-pip-version-check \
      --no-cache-dir \
      --require-hashes \
      --only-binary=:all: \
      -r requirements-lock-tools.lock
    /tmp/modacct-lock-tools/bin/python scripts/dependencies/generate_container_lock.py
  '
