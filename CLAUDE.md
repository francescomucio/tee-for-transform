# CLAUDE.md

Standing rules for working in this repository. Keep this file short — hard
rules plus pointers. Detail and rationale live in the linked docs, not here.

## Hard rules

- **Use the `t4t` logging module for all run/CLI output — never raw
  `print()` or ad hoc `typer.echo()`**, beyond one-off CLI argument-validation
  errors. Get a logger with `logger = logging.getLogger(__name__)` and call
  `logger.info(...)`/`logger.warning(...)`/`logger.error(...)`. Full
  rationale, examples, and the exception's exact scope:
  [`docs/development/contributing.md`](docs/development/contributing.md#logging-not-print-typerecho)
  (Code Style section).
- **Never interpolate secrets into a log message string.** Pass structured
  data via `extra={...}` so `--log-format json`'s redaction
  (`redact_secrets()`, applied centrally in `JSONFormatter`) can actually
  catch it — a secret baked into the message text bypasses redaction
  entirely. See [`docs/development/logging.md`](docs/development/logging.md).
- **Never `git commit`, `git push`, or open a PR unless explicitly asked.**
- **Never merge a PR yourself.**

## Pointers

- Logging conventions (detail): `docs/development/contributing.md` — Code
  Style section.
- JSON log schema (the six named lifecycle events): `docs/development/logging.md`.
- Code review checklist, including logging-specific danger zones:
  `docs/development/code-review.md`.
- Contribution workflow, testing guidelines, project structure:
  `docs/development/contributing.md`.
- Architecture overview: `docs/development/architecture.md`.
