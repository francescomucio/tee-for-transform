"""Structured logging setup for t4t CLI output.

This module is the single place that decides *how* run/build/test output is
rendered (``--log-format text|json`` / ``T4T_LOG_FORMAT``). It replaces the
raw ``print()``/``typer.echo()`` calls that used to carry t4t's user-facing
output, plus the handful of ad hoc `logging.basicConfig` calls, with one
handler wired to the standard library ``logging`` hierarchy that
``logging.getLogger(__name__)`` already uses throughout the codebase.

Design (see GitHub issue #36 for the full rationale):

* ``TextFormatter`` is a byte-compatible passthrough of ``record.getMessage()``
  -- today's text output is unchanged for every pre-existing message.
* ``JSONFormatter`` emits one flat JSON object per line (JSONL) to stdout.
  Every line has ``ts``/``level``/``msg``. Only six named lifecycle events
  (``run_started``, ``model_started``, ``model_finished``, ``test_started``,
  ``test_finished``, ``run_finished``) additionally carry a ``type`` field
  plus their own event-specific fields, passed via the stdlib ``extra={}``
  mechanism -- no nested envelope, no custom event-bus abstraction.
* Format selection is a ``name -> Formatter class`` registry (:data:`FORMATTERS`),
  not an if/elif chain, so adding a new format later is a one-line addition.
* Only records emitted by the modules in :data:`CLI_OUTPUT_LOGGER_NAMES` are
  ever written to stdout by the handler this module installs. Every other
  ``logging.getLogger(__name__)`` call site in the codebase (engine/adapter
  internals, parser internals, etc.) keeps behaving exactly as it did before
  this issue -- nothing about those call sites is removed or bypassed, they
  are simply not part of the curated stdout stream. This is what keeps
  "text output unchanged" true: before this issue, none of that internal
  logging ever reached stdout either (see the issue's audit).
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from t4t.adapters.base.config import redact_secrets

DEFAULT_LOG_FORMAT = "text"

#: Logger names (``__name__`` of the CLI command modules and ``t4t.executor``)
#: whose records are *unconditionally* eligible for the stdout text/JSON
#: stream this module configures. Every message in these modules used to be
#: a ``print()``/``typer.echo()`` call -- i.e. already, unconditionally, on
#: stdout -- so the swap to ``logger.*`` preserves that without needing a
#: second condition. Kept deliberately small: these are the modules whose
#: *entire* pre-existing logging.getLogger(__name__) surface was print()/
#: typer.echo() before this issue (constraint 4's scope), so nothing else
#: in them could leak.
CLI_OUTPUT_LOGGER_NAMES: frozenset[str] = frozenset(
    {
        "t4t.executor",
        "t4t.cli.commands.run",
        "t4t.cli.commands.build",
        "t4t.cli.commands.test",
    }
)

#: Logger names of modules that mix (a) messages this issue deliberately
#: surfaces on stdout -- either a pre-existing print()/typer.echo() call
#: site mechanically swapped to logger.*, tagged ``extra={"cli_output":
#: True}`` at the call site, or one of the six named lifecycle events,
#: tagged ``extra={"type": ...}`` -- with (b) *other*, pre-existing
#: ``logging.getLogger(__name__)`` calls that were never on stdout before
#: (e.g. compiler.py's test-library-merge diagnostics, or
#: "Starting execution of N models..." in model_executor.py). Only records
#: carrying one of those two markers are let through; everything else from
#: these loggers is filtered out, exactly as it was before this issue wired
#: up a handler (it's still visible on stderr via the pre-existing
#: logging.basicConfig-based setup, unaffected by this issue).
GATED_LOGGER_NAMES: frozenset[str] = frozenset(
    {
        "t4t.compiler",
        "t4t.executor_helpers.build_helpers",
        "t4t.parser.output.json_exporter",
        "t4t.parser.output.report_generator",
        "t4t.engine.executors.model_executor",
        "t4t.testing.executors.model_test_executor",
        "t4t.testing.executors.function_test_executor",
    }
)

#: LogRecord attributes that exist on every record regardless of what the
#: call site passed via ``extra={}``. Anything else found on the record is
#: treated as a structured field the call site deliberately attached.
_STANDARD_RECORD_ATTRS: frozenset[str] = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
        "message",
    }
)


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    """Return the caller-supplied ``extra={...}`` fields attached to *record*."""
    return {
        key: value for key, value in record.__dict__.items() if key not in _STANDARD_RECORD_ATTRS
    }


def _redact(value: Any) -> Any:
    """Redact secret values in *value* before it is serialized.

    Applies :func:`redact_secrets` to any dict-shaped value (connection
    config and similar structures are the realistic leak vector); scalars
    and lists pass through unchanged. This is the single enforcement point
    for redaction -- call sites pass raw config via ``extra`` and do not
    need to remember to redact it themselves.
    """
    if isinstance(value, dict):
        return redact_secrets(value)
    return value


class TextFormatter(logging.Formatter):
    """Passthrough formatter: byte-compatible with today's print()/echo() output."""

    def format(self, record: logging.LogRecord) -> str:
        text = record.getMessage()
        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            text = f"{text}\n{exc_text}" if text else exc_text
        return text


class JSONFormatter(logging.Formatter):
    """Flat JSONL formatter.

    ``ts``/``level``/``msg`` are always present. If the call site passed
    ``type`` via ``extra={}`` it is one of the six documented lifecycle
    events and the rest of ``extra`` is included flat (no nested envelope).
    Any other ``logger.*`` call still renders as valid JSON, just without a
    ``type`` -- the schema is only documented/stable for the six named
    events (see docs/development/logging.md).
    """

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds")
        ts = ts.replace("+00:00", "Z")

        payload: dict[str, Any] = {
            "ts": ts,
            "level": record.levelname.lower(),
        }

        extra = _extra_fields(record)
        event_type = extra.pop("type", None)
        run_id = extra.pop("run_id", None)
        if event_type is not None:
            payload["type"] = event_type
        if run_id is not None:
            payload["run_id"] = run_id

        payload["msg"] = record.getMessage()

        for key, value in extra.items():
            payload[key] = _redact(value)

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


#: name -> Formatter class registry, keyed by ``--log-format``/``T4T_LOG_FORMAT``.
#: A dict lookup (not an if/elif chain) so adding a future format (e.g. a
#: dbt-compatible one, deliberately deferred -- see issue #36 non-goals) is a
#: one-line addition here, not a rework of the call sites.
FORMATTERS: dict[str, type[logging.Formatter]] = {
    "text": TextFormatter,
    "json": JSONFormatter,
}

#: Marker attribute used to find and replace a handler this module
#: previously installed on the root logger, so repeated CLI invocations in
#: the same process (e.g. the test suite) don't stack duplicate handlers.
_HANDLER_MARKER = "_t4t_cli_output_handler"


class _DynamicStdoutHandler(logging.StreamHandler):
    """A StreamHandler that re-reads ``sys.stdout`` on every emit.

    Plain ``logging.StreamHandler(stream=sys.stdout)`` binds whatever
    ``sys.stdout`` object happens to exist at handler-construction time --
    it does not notice later reassignment. That is a mismatch with how
    ``print()``/``typer.echo()`` (and pytest's own stdout capture) behave:
    they resolve ``sys.stdout`` fresh on every call, so e.g.
    ``unittest.mock.patch("sys.stdout", new=StringIO())`` transparently
    redirects them. Re-reading it here keeps that same behavior for the
    logging-based replacement.
    """

    def emit(self, record: logging.LogRecord) -> None:
        stream = sys.stdout
        if stream is None:
            # sys.stdout can legitimately be None (e.g. pythonw.exe, or any
            # environment that detaches/closes standard streams) -- without
            # this guard, StreamHandler.emit() would try to write to a None
            # stream and rely on its own except-Exception/handleError()
            # fallback to avoid crashing, which prints a warning of its own
            # and can itself raise if handleError() tries to write to
            # sys.stderr (also unavailable here). Fall back to stderr, and
            # if that is unavailable too, drop the record silently rather
            # than raising -- there's nowhere sane left to put it.
            stream = sys.stderr
            if stream is None:
                return
        self.stream = stream
        super().emit(record)


class _CliOutputFilter(logging.Filter):
    """Only pass records eligible for t4t's curated stdout output stream.

    Records from :data:`CLI_OUTPUT_LOGGER_NAMES` pass unconditionally (every
    message in those modules used to be an unconditional print()/echo()).
    Records from :data:`GATED_LOGGER_NAMES` only pass if they carry a
    ``type`` (one of the six named lifecycle events) or ``cli_output=True``
    (a mechanically-swapped former print()/echo() call site) marker -- those
    modules also have other, pre-existing logging that was never on stdout
    before this issue and must stay that way.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return _is_curated_record(record)


def _is_curated_record(record: logging.LogRecord) -> bool:
    """True for a record this module's own handler would print.

    Used by :class:`_ExcludeCuratedFilter` to keep a *different*,
    pre-existing handler on the root logger (e.g. the
    ``logging.basicConfig``-installed one from ``t4t/cli/utils.py:
    setup_logging()``, which predates this module and formats every record
    it sees as ``LEVEL - name - msg`` to stderr) from also printing the same
    content a second time.
    """
    if record.name in CLI_OUTPUT_LOGGER_NAMES:
        return True
    if record.name in GATED_LOGGER_NAMES:
        extra = _extra_fields(record)
        return "type" in extra or extra.get("cli_output") is True
    return False


class _ExcludeCuratedFilter(logging.Filter):
    """Attached to any *other* handler already on the root logger so it does
    not also print t4t's curated stdout content a second time.

    Only :data:`GATED_LOGGER_NAMES` loggers need this: :data:`CLI_OUTPUT_LOGGER_NAMES`
    loggers are detached from root entirely (``propagate=False``, see
    :func:`configure_logging`) since their whole surface is curated content
    with nothing else that needs to keep reaching other handlers. GATED_LOGGER_NAMES
    loggers mix curated content with genuine, pre-existing diagnostic-only
    logging on the *same* logger name, so they can't be blanket-detached
    without also silencing that diagnostic content on its pre-existing
    (e.g. stderr) destination -- this filter is the surgical alternative:
    let everything from those loggers keep propagating and reaching other
    handlers as before, just not the specific records our own handler
    already printed.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return not _is_curated_record(record)


def resolve_log_format(value: str | None, *, strict: bool = False) -> str:
    """Normalize a requested log format string -- the single source of
    truth for log-format normalization, used both by internal callers (e.g.
    :func:`configure_logging`) and by the CLI's ``--log-format`` callback
    (:func:`t4t.cli.main.validate_log_format`), so the two never drift into
    subtly different normalization rules again (they used to: the CLI
    callback only lowercased, this function also stripped whitespace, so
    e.g. a stray-whitespace ``T4T_LOG_FORMAT=" json"`` env var would pass
    here but fail CLI validation).

    Args:
        value: Raw format string (e.g. from ``--log-format``/
            ``T4T_LOG_FORMAT``), or None.
        strict: If True, raise :class:`ValueError` for a value that does not
            normalize to a recognized format, instead of silently falling
            back to :data:`DEFAULT_LOG_FORMAT`. Internal callers (e.g.
            :func:`configure_logging`) must use the default, permissive
            ``strict=False`` -- they run *after* CLI validation has already
            had its chance to reject bad input, and must never raise on
            their own. The CLI callback opts into ``strict=True`` so bad
            user input is still rejected outright, as before.

    Returns:
        A key from :data:`FORMATTERS`.

    Raises:
        ValueError: If ``strict`` is True and ``value`` does not normalize
            to a recognized format.
    """
    normalized = value.strip().lower() if value is not None else None
    if normalized in FORMATTERS:
        return normalized
    if strict:
        raise ValueError(
            f"Invalid log format {value!r}. Must be one of: {', '.join(sorted(FORMATTERS))}."
        )
    return DEFAULT_LOG_FORMAT


def _install_legacy_root_handler(verbose: bool) -> None:
    """Ensure the pre-existing (predates this module), basicConfig-based
    root handler exists, before anything else in :func:`configure_logging`
    runs -- so :func:`_exclude_curated_records_from_other_root_handlers`
    always has a handler to patch, regardless of call order.

    This logic used to live only in ``t4t/cli/utils.py:setup_logging()``,
    called *separately* by ``CommandContext.__init__`` and required to run
    strictly before :func:`configure_logging` -- an implicit, unenforced
    ordering dependency that, if a future edit ever swapped the two calls,
    would silently reintroduce the duplicate-stderr-output bug (the
    exclusion filter would have nothing to attach to, since
    ``logging.basicConfig()`` is a no-op once *our* handler already exists
    on root). Owning it here, as this function's first step, removes that
    footgun by construction: there is exactly one function
    (:func:`configure_logging`) callers need to invoke, and its own
    internal ordering can't be violated from outside it.
    ``t4t/cli/utils.py:setup_logging()`` is now a thin wrapper around this
    same function, kept for backward compatibility with any external caller
    of that public name.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s - %(name)s - %(message)s")


def _remove_previously_installed_handlers() -> None:
    """Remove any handler this module previously attached, wherever it put it."""
    for logger_obj in [
        logging.getLogger(),
        *(logging.getLogger(n) for n in CLI_OUTPUT_LOGGER_NAMES),
    ]:
        for existing in list(logger_obj.handlers):
            if getattr(existing, _HANDLER_MARKER, False):
                logger_obj.removeHandler(existing)


def _exclude_curated_records_from_other_root_handlers(handler: logging.Handler) -> None:
    """Stop pre-existing (non-t4t) root handlers from also printing curated records.

    ``t4t/cli/utils.py:setup_logging()`` calls ``logging.basicConfig(...)``,
    which -- if nothing has installed a root handler yet -- attaches its own
    plain ``StreamHandler`` (stderr, ``"LEVEL - name - msg"`` format) to the
    root logger. GATED_LOGGER_NAMES loggers still propagate to root (see
    :func:`configure_logging`), so without this, every curated record from
    those modules would print twice: once via *this* module's handler
    (correctly, once, to stdout) and once via that older handler (a raw,
    unfiltered duplicate on stderr) -- doubling stderr output for a
    successful run and falsifying "text output unchanged".
    """
    for other in logging.getLogger().handlers:
        if other is handler:
            continue
        if any(isinstance(f, _ExcludeCuratedFilter) for f in other.filters):
            continue
        other.addFilter(_ExcludeCuratedFilter())


def configure_logging(log_format: str = DEFAULT_LOG_FORMAT, verbose: bool = False) -> None:
    """Install the single stdout handler that renders t4t's run/build/test output.

    Safe to call multiple times (e.g. once per CLI command invocation, or
    repeatedly across a test session) -- a previous handler installed by
    this function is removed first so records are never emitted twice.

    Two different attachment strategies, by design (see
    :data:`CLI_OUTPUT_LOGGER_NAMES` / :data:`GATED_LOGGER_NAMES` docstrings):

    * :data:`CLI_OUTPUT_LOGGER_NAMES` loggers get the handler attached
      *directly* and stop propagating to root (``propagate=False``) --
      their entire surface is curated content, so there is nothing else on
      those loggers that needs to keep reaching other handlers.
    * :data:`GATED_LOGGER_NAMES` loggers keep propagating to root as before
      (they mix curated content with genuine, pre-existing diagnostic
      logging that must keep reaching wherever it went before this issue);
      the handler is attached to root to catch their curated records, and
      any *other* pre-existing root handler gets an
      :class:`_ExcludeCuratedFilter` so it does not also print those same
      curated records a second time.

    This does not touch any other handler already attached to the root
    logger beyond adding that filter -- e.g. the legacy
    ``logging.basicConfig``-installed handler (installed by this function
    itself, first -- see :func:`_install_legacy_root_handler`) keeps
    working exactly as before for every record that isn't part of t4t's
    curated stdout stream.
    """
    # Must run before anything else below: _exclude_curated_records_from_
    # other_root_handlers() needs the legacy handler to already exist.
    # Owning this call here (rather than requiring some other function to
    # run first) is what makes that guarantee unconditional -- see the
    # docstring on _install_legacy_root_handler for the bug this replaced.
    _install_legacy_root_handler(verbose)

    formatter_cls = FORMATTERS.get(resolve_log_format(log_format), TextFormatter)

    _remove_previously_installed_handlers()

    handler = _DynamicStdoutHandler(stream=sys.stdout)
    handler.setFormatter(formatter_cls())
    handler.addFilter(_CliOutputFilter())
    handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    setattr(handler, _HANDLER_MARKER, True)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    _exclude_curated_records_from_other_root_handlers(handler)

    # The root logger's own level must not gate the allowlisted loggers'
    # records before they even reach the handler above; each allowlisted
    # logger is set explicitly so verbosity is controlled by the handler,
    # not by having to raise the root logger's level (which would also
    # raise the effective level of every other logger in the hierarchy).
    for name in CLI_OUTPUT_LOGGER_NAMES | GATED_LOGGER_NAMES:
        logging.getLogger(name).setLevel(logging.DEBUG if verbose else logging.INFO)

    # CLI_OUTPUT_LOGGER_NAMES: attach the same handler directly and stop
    # propagating to root -- avoids the doubled-stderr-output bug for the
    # modules whose whole logging surface is curated content, without
    # needing a filter (nothing else on these loggers should ever print).
    for name in CLI_OUTPUT_LOGGER_NAMES:
        logger_obj = logging.getLogger(name)
        if handler not in logger_obj.handlers:
            logger_obj.addHandler(handler)
        logger_obj.propagate = False
