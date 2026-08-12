# QuantLab v0.2.1 Release Guide

## Freeze Check

Before building, require a clean worktree, the expected version, offline test success, and no
running QuantLab process or occupied test port. Do not build from an uncommitted tree.

```powershell
git status --short
.venv\Scripts\python -c "from quant_lab import __version__; print(__version__)"
```

The expected version is `0.2.1`.

## Quality Gate

```powershell
$env:QUANTLAB_OFFLINE = "1"
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
.venv\Scripts\python -m coverage run --branch -m unittest discover -s tests
.venv\Scripts\python -m coverage report --fail-under=85

pnpm --dir frontend format:check
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test
pnpm --dir frontend build
pnpm --dir frontend e2e
```

All automated tests must remain offline. The optional real-provider smoke is not a release input
and must never rewrite fixed examples.

## History-Free Public Export

The private development object database is not published. Export the final committed tree to an
empty directory outside the internal repository:

```powershell
.venv\Scripts\python scripts\prepare_public_repository.py `
    --output ..\quantlab-public
```

Review `PUBLIC_EXPORT_MANIFEST.json` and `PUBLIC_EXPORT_SHA256SUMS.txt`, run the clean-room quality
gate inside the exported source, and initialize a new `main` Git history only with an explicitly
provided public author name and GitHub noreply or public email address.

## Windows Build

The formal build writes exactly one release archive and checksum:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\windows\build_release.ps1
```

Outputs:

```text
release/
  QuantLab-v0.2.1-windows-x64.zip
  SHA256SUMS.txt
```

The archive contains `QuantLab.exe`, `README-WINDOWS.txt`, the MIT license, Python third-party
notices, and frontend third-party notices.

## Packaged Smoke

Run the browser-free, bounded smoke test with a unique port:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\run_windows_smoke_watchdog.ps1 `
  -Executable dist\windows\QuantLab\QuantLab.exe `
  -Port 32117 `
  -TimeoutSeconds 120
```

Require `OFFLINE_FIXTURE_OK`, `HTTP_READY`, `SERVICE_STOPPED`, `PORT_RELEASED`, exit code `0`, and
no residual process. Then audit the ZIP for one `QuantLab/` root, licenses, frontend production
assets, absence of tests/logs/databases/private paths, and a matching SHA256.

## GitHub Boundary

`.github/workflows/release.yml` runs only for a pushed `v*` tag and verifies that the tag matches
the package version. Creating the repository, remote, tag, GitHub Release, or public visibility is
a separate manual approval step.

The first public release uses [RELEASE-NOTES-v0.2.1.md](../RELEASE-NOTES-v0.2.1.md). The Windows
binary is unsigned; SmartScreen may report an unknown publisher.
