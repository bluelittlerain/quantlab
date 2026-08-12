# Contributing To QuantLab

QuantLab is feature-frozen around one reproducible Hong Kong daily-research workflow. Focused
fixes that improve correctness, tests, documentation, security, accessibility, or maintainability
are welcome. Feature expansion should be justified by actual research use.

## Before Opening A Change

- Describe observable behavior and a minimal reproduction.
- Do not include API keys, personal trading data, local absolute paths, raw provider payloads, or
  unredacted logs.
- Do not propose brokerage credentials, live order submission, or profit guarantees.
- Changes to execution, fees, adjustments, metrics, or fingerprints require a specification update
  and an independently reviewable golden case before production code changes.

## Local Setup

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install --require-hashes -r requirements.lock
.venv\Scripts\python -m pip install --no-build-isolation --no-deps -e .
pnpm --dir frontend install --frozen-lockfile
```

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
```

Tests must remain deterministic and offline. Do not regenerate fixed examples from live Yahoo
data or weaken G01-G13/HK01-HK15 expected values to accommodate an implementation.

## Pull Requests

Keep each pull request focused. Explain the problem, chosen behavior, affected assumptions, and
exact verification commands. Update public documentation when a user-visible contract or
limitation changes.
