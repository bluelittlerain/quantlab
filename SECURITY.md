# Security Policy

QuantLab v0.2.1 is a quantitative research prototype. It has no brokerage connection, order
submission, trading-account authentication, or API-key workflow.

## Reporting A Vulnerability

Use GitHub Private Vulnerability Reporting when it is enabled for the public repository. Do not
post credentials, cookies, API keys, personal trading data, browser profiles, raw market caches,
or unredacted local paths in a public issue.

If private reporting is unavailable, use a private contact method listed on the repository
owner's GitHub profile and provide only the minimum redacted reproduction. A useful report names
the QuantLab version, operating system, launch method, affected endpoint, expected behavior, and
a minimal reproduction.

## Security Boundaries

- Desktop mode binds to loopback and opens an isolated Edge or Chrome profile.
- Optional private-LAN mode is explicit opt-in and uses a per-process pairing session; it is not
  an Internet authentication system.
- Market-provider access is isolated behind one adapter and blocked by the offline test gate.
- SQLite history, market cache, logs, and browser profiles live outside the source and Release ZIP.
- Windows binaries are not code-signed. Verify the published SHA256 before running an archive.
- Backtest output is research data, not an investment recommendation or security guarantee.
