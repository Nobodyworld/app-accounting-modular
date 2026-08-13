[CmdletBinding()]
param(
    [string]$Docker = "docker"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$baseImage = "python:3.14-slim@sha256:a7fb1e634c4a578f9e0bd6327f11a3cde11b7a9395f48e24360c0988bcc5c2bc"
$mount = "type=bind,source=$repositoryRoot,target=/workspace"

& $Docker run --rm `
    --platform linux/amd64 `
    --mount $mount `
    --workdir /workspace `
    --env HOME=/tmp/modacct-lock-home `
    --env UV_CACHE_DIR=/tmp/modacct-uv-cache `
    $baseImage `
    sh -euc @'
python -m venv /tmp/modacct-lock-tools
/tmp/modacct-lock-tools/bin/python -m pip install \
  --disable-pip-version-check \
  --no-cache-dir \
  --require-hashes \
  --only-binary=:all: \
  -r requirements-lock-tools.lock
/tmp/modacct-lock-tools/bin/python scripts/dependencies/generate_container_lock.py
'@

if ($LASTEXITCODE -ne 0) {
    throw "Container lock generation failed with exit code $LASTEXITCODE"
}
