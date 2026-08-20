## What

<!-- One-paragraph summary of the change. -->

## Why

<!-- Motivation / linked issue. -->

## Checklist

- [ ] `python3 tests/test_text_mirror.py` passes
- [ ] `ruff check scripts/ tests/` clean
- [ ] CLI surface changes reflected in `SKILL.md`, `README.md`, and `docs/`
- [ ] Server security invariants untouched (127.0.0.1 bind, Origin allowlist,
      `client_out_file` confinement) — or change flagged for security review
