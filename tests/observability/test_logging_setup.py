"""
Unit tests for t4t.observability.logging_setup: TextFormatter, JSONFormatter,
the format registry, and the stdout eligibility filter.

See tests/cli/test_logging_e2e.py for subprocess-level acceptance tests
(run_id join across the JSON stream and runs.sqlite, the redaction test
against a real invocation, and JSONL well-formedness for `t4t run`).
"""

import json
import logging

import pytest

from t4t.observability.logging_setup import (
    FORMATTERS,
    JSONFormatter,
    TextFormatter,
    _CliOutputFilter,
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
