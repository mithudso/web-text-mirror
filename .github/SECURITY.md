# Security Policy

## Reporting

Open a private security advisory on GitHub
(https://github.com/mithudso/web-text-mirror/security/advisories/new) or contact the
repository owner (@mithudso) directly. Please do not open public issues for
exploitable problems.

## Scope notes

The local HTTP API (`--serve`) is designed to be reachable only from the same machine
(127.0.0.1 bind, Origin allowlist, output-filename confinement). Reports that weaken
any of those invariants are in scope. The crawler intentionally fetches arbitrary
public URLs supplied by its operator — that is its function, not a vulnerability.

See `docs/SECURITY.md` for the threat model.
