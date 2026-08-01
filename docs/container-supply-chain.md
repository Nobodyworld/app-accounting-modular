# Reproducible Container Supply Chain

This guide defines how the API and Streamlit container dependencies are
resolved, installed, checked, and attested. It covers dependency and build
evidence only; it does not publish images, approve a release, or change
application behavior.

## Policy artifacts

| Artifact | Role |
| --- | --- |
| `requirements.txt` | Human-reviewed, bounded compatibility manifest and the sole runtime resolution input. |
| `requirements-dev.txt` | Human-reviewed development and quality-tool compatibility manifest. |
| `requirements-container.lock` | Generated Python 3.14/Linux runtime graph with exact versions and hashes. |
| `requirements-lock-tools.lock` | Exact, hashed lock for the generator; it is not installed in application images. |

The committed runtime lock contains 84 packages: 19 direct requirements and 65
transitive requirements. Its SHA-256 is
`990aa39c04686870f6907074b32d01eff81f69f84f9281d98aefa91fb72163d9`.
The lock preserves required extras such as `uvicorn[standard]` and
`PyJWT[crypto]`.

The runtime lock header records the canonical-LF SHA-256 of its input. The
current `requirements.txt` fingerprint is
`9cb72bf6c119404c7d9c85aaf0c0bc737d272bd5928c0b8200f41fffbefbf34d`.
Line endings are normalized to LF for this fingerprint so Windows and Linux
checkouts have the same policy identity; the lock-file checksums in this guide
are ordinary byte-for-byte SHA-256 values.

## Pinned Python base

Both application Dockerfiles use the same official manifest-list reference:

```text
python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6
```

On 2026-07-31, the tag was resolved with registry-aware Docker Buildx tooling:

```bash
docker buildx imagetools inspect docker.io/library/python:3.14-slim
```

The output identified the official `docker.io/library/python` image, the OCI
manifest-list digest shown above, and a `linux/amd64` manifest. The image
reported Python 3.14.6 on the `slim-trixie` variant. This is a registry manifest
digest, not a local Docker image ID.

When updating the base, repeat the inspection rather than copying a digest from
an unverified source. Confirm the official image owner and `linux/amd64`
manifest, update both Dockerfiles and the policy constants together, regenerate
the lock metadata, and review the complete diff. A mutable build argument may
not replace the pinned base.

## Locked generator

Runtime locking uses `uv==0.12.0`. The one-entry tool lock has SHA-256
`2522c140fe61233b873b30a8cb54e613e80f2c4bea1ea39f64e21f37b2a4d51a`.
It records the hash of the official Linux x86-64 manylinux wheel and installs
with `--require-hashes` and `--only-binary=:all:` inside the pinned base image.

The initial bootstrap was intentionally separate from routine generation: an
isolated virtual environment installed exactly `uv==0.12.0`, and the official
manylinux wheel was selected and its SHA-256
`cbff74f884846d794713670faf8abe10db3bd70c43b01e63223f74eb7d958689`
was reviewed before committing `requirements-lock-tools.lock`. No global tool
installation is trusted. After bootstrap, routine generation creates a fresh
virtual environment inside the pinned Python image and installs only the hashed
tool lock before invoking the compiler.

## Generate and verify the runtime lock

Regeneration is an intentional, networked dependency-update operation. From a
Windows checkout with Docker Desktop:

```powershell
pwsh scripts/dependencies/Generate-ContainerLock.ps1
```

On Linux or in a CI-compatible shell with Docker:

```bash
sh scripts/dependencies/generate-container-lock.sh
```

Both wrappers run on `linux/amd64` in the same digest-pinned Python 3.14 image,
install the hashed tool lock, require binary distributions, compile
`requirements.txt`, and write stable LF output plus generator metadata. Given
the same inputs and package-index state, repeated generation produces the same
lock.

Normal validation does not contact PyPI or modify the lock:

```bash
python scripts/dependencies/verify_container_lock.py
pytest -q tests/test_container_supply_chain.py
```

The verifier fails on an input-fingerprint change, missing or inconsistent
metadata, non-exact or unhashed requirements, duplicate entries, editable/VCS
or direct-URL sources, missing top-level dependencies or extras, a mutable
index option, or a Python/platform/base-image policy mismatch. A newly released
package therefore cannot break an unrelated pull request.

After intentional regeneration, review direct and transitive version changes,
then run:

```bash
python -m pip_audit --require-hashes --disable-pip -r requirements-container.lock
```

`pip-audit` uses current vulnerability data and is a security assessment, not a
proof that the dependency resolver is deterministic.

## Fail-closed image installation

Both Dockerfiles copy `requirements-container.lock`, never `requirements.txt`,
and use this installation policy:

```dockerfile
RUN python -m pip install \
      --disable-pip-version-check \
      --no-cache-dir \
      --require-hashes \
      --only-binary=:all: \
      --no-deps \
      -r requirements-container.lock \
    && python -m pip check
```

Every transitive dependency must therefore be explicit and hashed. `--no-deps`
prevents installation-time resolution, and `--only-binary=:all:` prevents an
sdist from starting an unpinned build-isolation environment. A missing or
altered hash fails the build. The pip version already supplied by the pinned
base remains part of that base; application image builds do not upgrade pip,
setuptools, or wheel.

Build clean images directly with:

```bash
docker build --no-cache -f config/Dockerfile.api -t modacct-api:repro-a .
docker build --no-cache -f config/Dockerfile.api -t modacct-api:repro-b .
docker build --no-cache -f config/Dockerfile.web -t modacct-web:repro-a .
docker build --no-cache -f config/Dockerfile.web -t modacct-web:repro-b .
```

Repeated-build review compares the pinned base, `pip freeze --all`, normalized
package/version inventory, runtime-lock checksum, SBOM package inventory,
numeric non-root user, entrypoint, and health behavior. It does not require
identical image IDs.

## SBOM and image evidence

The supply-chain CI job scans each built image with Syft 1.50.0 through
`anchore/sbom-action`, producing separate SPDX JSON documents for the API and
web images. The job rejects empty SBOMs or documents that do not identify the
expected image and computes a SHA-256 for each SBOM.

For each image, the 14-day workflow artifact contains an exported
image archive, archive SHA-256, Docker image ID and configuration summary,
pinned base reference, Syft-observed platform-manifest digest, runtime-lock
SHA-256, installed package inventory, SPDX JSON SBOM and its SHA-256, source
commit, and workflow-run metadata. These run-specific archives and SBOMs are
never committed.

The actions used by the CI workflow were resolved from their official
publishers on 2026-07-31 and are executable only at full commit SHAs:

| Repository | Release | Release date | Full commit SHA | Purpose |
| --- | --- | --- | --- | --- |
| `actions/checkout` | `v7.0.1` | 2026-07-20 | `3d3c42e5aac5ba805825da76410c181273ba90b1` | Credential-free source checkout. |
| `actions/setup-python` | `v7.0.0` | 2026-07-20 | `5fda3b95a4ea91299a34e894583c3862153e4b97` | Python 3.12/3.13/3.14 quality matrix. |
| `actions/upload-artifact` | `v7.0.1` | 2026-04-10 | `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` | Upload 14-day ordinary evidence. |
| `actions/attest` | `v4.2.1` | 2026-07-29 | `508db95dd578ae2727ebd6217d5ba78e4fbda05d` | Build-provenance and SBOM attestations. |
| `anchore/sbom-action` | `v0.24.0` | 2026-03-20 | `e22c389904149dbc22b58101806040fa8d37a610` | SPDX JSON generation with Syft 1.50.0. |
| `actions/download-artifact` | `v8.0.1` | 2026-03-11 | `3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c` | Retrieve exact evidence for attestation. |

## Pull requests and trusted attestations

Pull-request runs, including fork pull requests, verify the locks, build and
smoke-test both images, prove least-privilege behavior and `pip check`, produce
inventories and SBOMs, verify checksums, and upload ordinary evidence. They do
not receive an OIDC token or publish attestations.

Attestation publication is restricted to trusted `push` runs on `main` and
trusted manual `workflow_dispatch` runs. Only the attestation job receives:

```yaml
permissions:
  contents: read
  id-token: write
  attestations: write
```

Workflow-level permissions remain `contents: read`. Provenance and SPDX SBOM
attestations bind to the exported image archives and their SHA-256 subjects.
Because this repository does not push an image to a registry, these are
archive-bound attestations and are not claims about a registry image.

After downloading evidence from a trusted run, verify its checksum first and
then verify the GitHub attestation, for example:

```powershell
$SourceSha = "<source-commit-sha>"
$Archive = ".\container-evidence\modacct-api-$SourceSha.tar"
$Expected = (Select-String -Path ".\container-evidence\image-archives.sha256" -Pattern "modacct-api-$SourceSha\.tar$").Line.Split()[0]
$Actual = (Get-FileHash -Algorithm SHA256 $Archive).Hash.ToLowerInvariant()
if ($Actual -ne $Expected) { throw "API archive checksum mismatch" }
gh attestation verify $Archive --repo Nobodyworld/app-accounting-modular
```

```bash
source_sha="<source-commit-sha>"
cd container-evidence
sha256sum --check image-archives.sha256
cd ..
gh attestation verify "container-evidence/modacct-api-${source_sha}.tar" --repo Nobodyworld/app-accounting-modular
```

Use the actual filenames from the downloaded workflow artifact and repeat the
verification for the web archive. Pull-request artifacts have checksums but no
published attestation by design.

## Dependency update flow

Dependabot retains weekly coverage for pip manifests, GitHub Actions, and
Dockerfiles. Generated artifacts still require maintainer follow-up:

- For a `requirements.txt` change or intentional transitive refresh, regenerate
  `requirements-container.lock`, review all direct and transitive changes, run
  the offline verifier and focused tests, run `pip-audit` against the lock, and
  rebuild both images.
- For a Python base update, resolve the official manifest list again, confirm
  `linux/amd64`, update both Dockerfiles and every policy/header reference, and
  regenerate and verify the lock even when package versions do not change.
- For an action update, verify the expected official publisher and current
  release, replace the executable reference with its full commit SHA, and keep
  the release tag and resolution date in the workflow comment.

Dependabot does not automatically make the custom runtime lock authoritative;
the reviewed regeneration step is required before merging an update.

## Ruff pin rationale

`ruff==0.15.21` remains exact in `requirements-dev.txt` because formatter and
linter output must remain stable, quality-gate behavior should be reproducible,
and formatting changes should receive deliberate review. Ruff is a development
quality tool and its pin is independent of the runtime container lock; it must
not be described as that lock.

## Known limits

- No image is published to a registry, so there is no registry-bound image
  provenance or SBOM attestation.
- Pull requests create 14-day evidence but publish no attestations;
  trusted attestations exist only after an eligible `main` push or manual run.
- Intentional lock regeneration observes the package index at that time. The
  committed hashed lock prevents normal CI and image builds from re-resolving
  newer releases.
- Dependency, base, package-inventory, and evidence resolution are
  reproducible. Docker timestamps and other build metadata are not normalized,
  so bit-for-bit image IDs are not promised.
- An image vulnerability scan is not included because a current pinned scanner
  with a reviewably deterministic vulnerability database was not established.
  A dynamic database could change results without a repository change.
  `pip-audit` remains the reviewed Python dependency vulnerability control.
- These controls provide build evidence; they do not constitute release
  approval or alter the repository's publication status.
