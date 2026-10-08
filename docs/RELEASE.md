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

pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend format:check
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test
pnpm --dir frontend build
pnpm --dir frontend exec playwright install chromium
pnpm --dir frontend e2e

# Launcher tests require the real frontend/dist produced above.
.venv\Scripts\python -m coverage run --branch -m unittest discover -s tests
.venv\Scripts\python -m coverage report --fail-under=85
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

The release has two separate workflows. A tag push **never creates a GitHub Release**.
Creating a repository, remote, tag, or changing public visibility remains a separately approved
operation. Existing tags and published assets must not be moved, recreated, or overwritten.

### 1. Build and Verify an Existing Annotated Tag

`.github/workflows/release.yml` runs on a pushed `v*` tag, or by manual dispatch with a required
`release_tag`. Dispatch can rebuild an existing annotated tag without changing it:

```powershell
gh workflow run release.yml --ref main -f release_tag=v0.2.1
```

The workflow resolves and records the full tag commit SHA and annotated tag object, verifies a
clean checkout and matching package version, and requires matching Release Notes. All product
checkouts use the resolved commit, not the dispatch branch. The workflow definition and release
guard/watchdog come from the workflow's own immutable SHA; this also supports validating older
tags that predate these orchestration changes.

Before the Windows build, the workflow calls `.github/workflows/ci.yml` with that exact SHA as a
required `workflow_call` input. Python 3.11/3.12 tests and branch coverage, frontend static checks,
and fixed-fixture Chromium E2E must all succeed. The build job uses `needs` on this entire reusable
CI gate. It cannot race an independent main/tag CI run or rely on a green check for another SHA.
Failure, cancellation, or skipped prerequisites prevent candidate upload and publication.

The Windows job retains its locked dependencies and Windows quality checks, builds the ZIP, and
runs the watchdog against the packaged `dist/windows/QuantLab/QuantLab.exe`. The watchdog has a
120-second limit, checks the offline fixture marker and lifecycle markers above, requires exit
code 0 and a released port, and cleans up its own process tree on failure. Smoke logs remain on
the runner and are not release assets.

Only after smoke succeeds is a read-only Actions artifact uploaded:
`windows-release-<full-tag-SHA>-<run-attempt>`, retained for 14 days. It contains the unchanged
Windows ZIP name, `SHA256SUMS.txt`, matching Release Notes, and `release-evidence.json`. The evidence
binds the files' hashes to the repository numeric ID, tag object, source SHA, build run and attempt.
No step in this workflow receives `contents: write`.

### 2. Review, Then Explicitly Approve Publication

Wait until the **entire** Windows Release build run is successful. Review the tag SHA, all CI jobs,
packaged smoke output, ZIP/checksum and Release Notes, and perform the required Windows manual
checks. Record the completed build run ID and full 40-character tag SHA.

Only then run **Publish approved Windows Release** (`publish-release.yml`) from `main` in GitHub
Actions. Enter the existing `release_tag`, reviewed `expected_sha`, successful `build_run_id`, and
explicitly check `approve_publication` (default: false). This dispatch is the manual approval for
a public, non-draft Release. Do not dispatch this workflow as part of automated tag creation.
Repository administrators may add environment reviewers as a further control; the required
manual dispatch does not depend on environment settings being configured.

The read-only verification job rejects an unfinished/failed build, the wrong workflow or event,
missing/expired/ambiguous artifacts, stale rerun artifacts, lightweight or moved tags, mismatched
provenance, changed bytes, and an already-existing Release (including drafts). Download selection
uses the verified immutable artifact ID and explicit build run ID, never a latest-artifact lookup.
The dispatched workflow SHA supplies the guard; product source is not rebuilt during publication.

Only the final publish job has `contents: write`. It downloads the same artifact ID and repeats
the tag, build attempt, evidence and SHA256 checks immediately before `softprops/action-gh-release`.
It publishes exactly `QuantLab-<tag>-windows-x64.zip`, `SHA256SUMS.txt` and `RELEASE-NOTES-<tag>.md`
with explicit `tag_name`, `draft: false`, and `prerelease: false`. Evidence is not a public asset.
Concurrent publishes for the same tag are serialized; an existing Release is never updated by this
workflow. If artifacts expire, rebuild and review a new successful candidate before approving it.

This policy applies after these workflow changes reach the default branch and future tags. The
already-published v0.2.1 tag, Release and ZIP remain unchanged. Testing the new guard for that version
must use offline fixtures: a real publication attempt for an existing Release deliberately fails.

The first public release uses [RELEASE-NOTES-v0.2.1.md](../RELEASE-NOTES-v0.2.1.md). The Windows
binary is unsigned; SmartScreen may report an unknown publisher.
