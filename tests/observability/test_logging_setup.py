"""
Unit tests for t4t.observability.logging_setup: TextFormatter, JSONFormatter,
the format registry, and the stdout eligibility filter.

See tests/cli/test_logging_e2e.py for subprocess-level acceptance tests
(run_id join across the JSON stream and runs.sqlite, the redaction test
against a real invocation, and JSONL well-formedness for `t4t run`).
"""

import json
import logging
from io import StringIO
from unittest.mock import patch

import pytest

from t4t.observability.logging_setup import (
    _HANDLER_MARKER,
    FORMATTERS,
    JSONFormatter,
    TextFormatter,
    _CliOutputFilter,
    _DynamicStdoutHandler,
    _ExcludeCuratedFilter,
    configure_logging,
    resolve_log_format,
)

_LOGGER = logging.getLogger("test.observability")


def _make_record(
    level: int = logging.INFO,
    msg: str = "hello",
    extra: dict | None = None,
    name: str = "test.observability",
) -> logging.LogRecord:
    """Build a real LogRecord the way stdlib logging would, extra and all."""
    return _LOGGER.makeRecord(name, level, "test_file.py", 1, msg, (), None, extra=extra)


class TestTextFormatter:
    def test_passthrough_message(self):
        record = _make_record(msg="Running t4t on project: demo")
        assert TextFormatter().format(record) == "Running t4t on project: demo"

    def test_ignores_extra_fields(self):
        """Text mode must be byte-compatible with the old print()/echo() content --
        structured fields passed via extra must never leak into the text line."""
        record = _make_record(
            msg="  ✅ my_schema.t (0.8s, 12,043 rows)",
            extra={
                "type": "model_finished",
                "run_id": "abc-123",
                "model": "my_schema.t",
                "status": "success",
                "duration_ms": 800,
                "row_count": 12043,
            },
        )
        assert TextFormatter().format(record) == "  ✅ my_schema.t (0.8s, 12,043 rows)"

    def test_percent_style_args_are_interpolated(self):
        record = _make_record(msg="")
        record = _LOGGER.makeRecord(
            "test.observability",
            logging.WARNING,
            "f.py",
            1,
            "Could not persist: %s",
            ("boom",),
            None,
        )
        assert TextFormatter().format(record) == "Could not persist: boom"


class TestJSONFormatter:
    def test_always_has_ts_level_msg(self):
        record = _make_record(msg="Refreshing generated lookup models...")
        payload = json.loads(JSONFormatter().format(record))
        assert {"ts", "level", "msg"} <= payload.keys()
        assert payload["level"] == "info"
        assert payload["msg"] == "Refreshing generated lookup models..."
        assert "type" not in payload
        assert "run_id" not in payload

    def test_ts_is_iso8601_utc_with_milliseconds(self):
        record = _make_record(msg="x")
        payload = json.loads(JSONFormatter().format(record))
        # e.g. "2026-07-23T09:14:02.113Z"
        assert payload["ts"].endswith("Z")
        assert "T" in payload["ts"]
        assert "." in payload["ts"]

    def test_named_lifecycle_event_carries_type_run_id_and_flat_fields(self):
        record = _make_record(
            msg="  ✅ my_schema.t (0.8s, 12,043 rows)",
            extra={
                "type": "model_finished",
                "run_id": "3f2a1e4c-0000-0000-0000-000000000000",
                "model": "my_schema.t",
                "status": "success",
                "duration_ms": 800,
                "row_count": 12043,
                "materialization": "table",
            },
        )
        payload = json.loads(JSONFormatter().format(record))
        assert payload["type"] == "model_finished"
        assert payload["run_id"] == "3f2a1e4c-0000-0000-0000-000000000000"
        # Flat -- no nested "data" envelope (Terraform-style, not dbt-style).
        assert payload["model"] == "my_schema.t"
        assert payload["status"] == "success"
        assert payload["duration_ms"] == 800
        assert payload["row_count"] == 12043
        assert payload["materialization"] == "table"
        assert "data" not in payload

    def test_generic_message_has_no_type_field_but_is_still_valid_json(self):
        record = _make_record(msg="Refreshing generated lookup models...")
        line = JSONFormatter().format(record)
        payload = json.loads(line)  # must not raise
        assert "type" not in payload

    def test_redacts_dict_valued_extra_field(self):
        """The formatter -- not the call site -- is responsible for redaction."""
        record = _make_record(
            msg="Resolved connection configuration",
            extra={
                "connection_config": {
                    "type": "postgresql",
                    "password": "sk-super-secret-value",
                    "host": "db.example.com",
                }
            },
        )
        line = JSONFormatter().format(record)
        assert "sk-super-secret-value" not in line
        payload = json.loads(line)
        assert payload["connection_config"]["password"] == "****"
        assert payload["connection_config"]["host"] == "db.example.com"

    def test_redaction_does_not_affect_non_secret_keys(self):
        record = _make_record(
            msg="x",
            extra={"connection_config": {"type": "duckdb", "path": "data/x.duckdb"}},
        )
        payload = json.loads(JSONFormatter().format(record))
        assert payload["connection_config"] == {"type": "duckdb", "path": "data/x.duckdb"}


class TestFormatterRegistry:
    def test_registry_has_exactly_text_and_json(self):
        assert set(FORMATTERS.keys()) == {"text", "json"}
        assert FORMATTERS["text"] is TextFormatter
        assert FORMATTERS["json"] is JSONFormatter

    @pytest.mark.parametrize("value", ["text", "TEXT", " Text "])
    def test_resolve_log_format_text(self, value):
        assert resolve_log_format(value) == "text"

    @pytest.mark.parametrize("value", ["json", "JSON"])
    def test_resolve_log_format_json(self, value):
        assert resolve_log_format(value) == "json"

    def test_resolve_log_format_falls_back_to_default_for_unknown(self):
        assert resolve_log_format("dbt-json") == "text"
        assert resolve_log_format(None) == "text"

    def test_resolve_log_format_strict_raises_for_unknown(self):
        """strict=True is what t4t/cli/main.py:validate_log_format() uses to
        reject bad --log-format input outright -- see
        TestValidateLogFormat below for the CLI-callback-level test."""
        with pytest.raises(ValueError, match="Invalid log format"):
            resolve_log_format("dbt-json", strict=True)

    @pytest.mark.parametrize("value", ["text", "TEXT", " Text ", "json", " json"])
    def test_resolve_log_format_strict_accepts_known_values(self, value):
        assert resolve_log_format(value, strict=True) == value.strip().lower()


class TestValidateLogFormat:
    """t4t.cli.main.validate_log_format() -- the --log-format Typer
    callback -- must delegate entirely to resolve_log_format(strict=True)
    rather than reimplementing its own, slightly different normalization.
    Regression coverage for the specific drift this replaced: the old
    callback only lowercased (no whitespace stripping), so a stray-whitespace
    value like " json" would pass resolve_log_format() but be rejected here,
    inconsistently."""

    @pytest.mark.parametrize("value", ["text", "TEXT", " json ", "JSON"])
    def test_accepts_and_normalizes_known_values(self, value):
        from t4t.cli.main import validate_log_format

        assert validate_log_format(value) == value.strip().lower()

    def test_rejects_unknown_value_with_bad_parameter(self):
        import typer

        from t4t.cli.main import validate_log_format

        with pytest.raises(typer.BadParameter):
            validate_log_format("dbt-json")


class TestCliOutputFilter:
    def test_unconditional_logger_always_passes(self):
        record = _make_record(name="t4t.cli.commands.run", msg="Running t4t on project: x")
        assert _CliOutputFilter().filter(record) is True

    def test_gated_logger_blocked_without_marker(self):
        """A pre-existing, non-lifecycle logger.debug/info call in a gated
        module (e.g. compiler.py's "Starting project compilation...") must
        NOT reach stdout -- it never did before this issue."""
        record = _make_record(
            name="t4t.compiler", msg="Starting project compilation to OTS modules"
        )
        assert _CliOutputFilter().filter(record) is False

    def test_gated_logger_passes_with_cli_output_marker(self):
        record = _make_record(
            name="t4t.compiler", msg="✅ No conflicts detected", extra={"cli_output": True}
        )
        assert _CliOutputFilter().filter(record) is True

    def test_gated_logger_passes_with_lifecycle_type_marker(self):
        record = _make_record(
            name="t4t.engine.executors.model_executor",
            msg="  ▶ my_schema.t",
            extra={"type": "model_started", "run_id": "x", "model": "my_schema.t"},
        )
        assert _CliOutputFilter().filter(record) is True

    def test_unrelated_logger_always_blocked(self):
        record = _make_record(
            name="t4t.adapters.duckdb.adapter", msg="Connected to DuckDB database: x"
        )
        assert _CliOutputFilter().filter(record) is False


class TestConfigureLoggingInstallsLegacyHandlerItself:
    """Structural regression test for the ordering footgun this module used
    to have: ``configure_logging()`` must install the legacy
    ``basicConfig``-based root handler itself (via
    ``_install_legacy_root_handler``, as its own first step), rather than
    depending on some *other* function (the old, separate
    ``t4t/cli/utils.py:setup_logging()`` call site) having run first. That
    used to be an implicit, unenforced ordering dependency between two call
    sites in ``CommandContext.__init__``; ``CommandContext`` now calls only
    ``configure_logging()``. This test proves the property structurally --
    by calling ``configure_logging()`` completely alone, with no prior
    logging setup of any kind -- rather than merely by convention/comment.
    """

    #: The exact ``basicConfig(format=...)`` string
    #: ``_install_legacy_root_handler`` uses -- distinguishes the legacy
    #: handler from pytest's own root-logger ``LogCaptureHandler``.
    _LEGACY_FMT = "%(levelname)s - %(name)s - %(message)s"

    @pytest.fixture(autouse=True)
    def _isolated_root_logger(self):
        """Save/restore the real root logger's handlers and level around
        each test, and start each test with a *clean* root logger (no
        handlers at all -- including pytest's own log-capture handler,
        which pytest re-attaches for the call phase after fixture setup
        runs, so it must be cleared inside the test body, not just here).

        This mirrors the real-world scenario the underlying bug is about: a
        fresh process where nothing has called ``logging.basicConfig()``
        yet, so ``configure_logging()`` alone is responsible for installing
        the legacy handler.
        """
        root = logging.getLogger()
        saved_handlers = list(root.handlers)
        saved_level = root.level
        yield root
        root.handlers = saved_handlers
        root.setLevel(saved_level)

    def _legacy_handlers(self, root: logging.Logger) -> list[logging.Handler]:
        return [
            h
            for h in root.handlers
            if not getattr(h, _HANDLER_MARKER, False)
            and getattr(h.formatter, "_fmt", None) == self._LEGACY_FMT
        ]

    def test_configure_logging_alone_installs_a_legacy_handler_with_exclude_filter(
        self, _isolated_root_logger
    ):
        """With *zero* prior logging setup (no separate basicConfig call
        from anywhere else -- e.g. the old, now-removed
        ``t4t/cli/utils.py:setup_logging()`` call site), configure_logging()
        alone must still end up with a legacy handler on root carrying an
        _ExcludeCuratedFilter -- proving the legacy handler is installed
        unconditionally as part of configure_logging() itself, not
        contingent on a separate, order-dependent caller running first."""
        root = _isolated_root_logger
        # Clear here, not only in the fixture: pytest's logging plugin
        # re-attaches its own capture handler for the call phase after
        # fixture setup runs, so this must happen right before the call
        # under test to reproduce a truly handler-free root logger.
        root.handlers = []
        assert self._legacy_handlers(root) == []

        configure_logging(log_format="text", verbose=False)

        legacy_handlers = self._legacy_handlers(root)
        assert legacy_handlers, "configure_logging() must install a legacy root handler itself"
        assert any(
            any(isinstance(f, _ExcludeCuratedFilter) for f in h.filters) for h in legacy_handlers
        ), "the legacy handler must carry the exclusion filter"

    def test_configure_logging_is_idempotent_across_repeated_calls(self, _isolated_root_logger):
        """Calling configure_logging() repeatedly (e.g. multiple CLI
        commands in one process, or a test session) must not keep stacking
        legacy handlers -- logging.basicConfig() is a no-op once a root
        handler already exists, so exactly one legacy handler should remain
        no matter how many times configure_logging() runs."""
        root = _isolated_root_logger
        root.handlers = []

        configure_logging(log_format="text", verbose=False)
        configure_logging(log_format="json", verbose=True)
        configure_logging(log_format="text", verbose=False)

        assert len(self._legacy_handlers(root)) == 1


class TestDynamicStdoutHandlerStdoutNone:
    """sys.stdout can legitimately be None (pythonw.exe, or any environment
    that detaches/closes standard streams) -- _DynamicStdoutHandler.emit()
    re-reads sys.stdout on every call (needed for test-mocking, e.g.
    unittest.mock.patch("sys.stdout", new=StringIO())), so it must guard
    against that rather than handing None to StreamHandler.emit()."""

    def _make_record(self, msg: str = "hello") -> logging.LogRecord:
        return logging.getLogger("test.dynamic_stdout").makeRecord(
            "test.dynamic_stdout", logging.INFO, "test_file.py", 1, msg, (), None
        )

    def test_falls_back_to_stderr_when_stdout_is_none(self):
        handler = _DynamicStdoutHandler()
        fake_stderr = StringIO()
        with (
            patch("sys.stdout", None),
            patch("sys.stderr", fake_stderr),
        ):
            handler.emit(self._make_record("hello"))
        assert "hello" in fake_stderr.getvalue()

    def test_does_not_raise_when_both_stdout_and_stderr_are_none(self):
        handler = _DynamicStdoutHandler()
        with patch("sys.stdout", None), patch("sys.stderr", None):
            handler.emit(self._make_record("hello"))  # must not raise

    def test_still_writes_to_stdout_normally_when_present(self):
        handler = _DynamicStdoutHandler()
        fake_stdout = StringIO()
        with patch("sys.stdout", fake_stdout):
            handler.emit(self._make_record("hello"))
        assert "hello" in fake_stdout.getvalue()
