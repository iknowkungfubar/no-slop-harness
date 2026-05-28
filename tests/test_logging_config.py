"""Test suite for structured logging configuration."""

from __future__ import annotations

import json
import logging

from no_slop_harness.logging_config import (
    JSONFormatter,
    PipelineLogger,
    configure_logging,
)


class TestJSONFormatter:
    """JSONFormatter produces valid structured JSON log entries."""

    def test_format_produces_valid_json(self) -> None:
        fmt = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=1,
            msg="hello world", args=(), exc_info=None,
        )
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test"
        assert parsed["message"] == "hello world"

    def test_format_includes_timestamp(self) -> None:
        fmt = JSONFormatter()
        record = logging.LogRecord(
            name="t", level=logging.WARNING, pathname="", lineno=1,
            msg="test", args=(), exc_info=None,
        )
        output = fmt.format(record)
        parsed = json.loads(output)
        assert "timestamp" in parsed
        assert parsed["level"] == "WARNING"

    def test_format_skips_standard_record_attrs(self) -> None:
        fmt = JSONFormatter()
        record = logging.LogRecord(
            name="t", level=logging.INFO, pathname="", lineno=1,
            msg="msg", args=(), exc_info=None,
        )
        output = fmt.format(record)
        parsed = json.loads(output)
        # Standard attrs should NOT be in "extra"
        assert "name" not in parsed.get("extra", {})
        assert "levelname" not in parsed.get("extra", {})
        assert "lineno" not in parsed.get("extra", {})


class TestPipelineLogger:
    """PipelineLogger attaches request_id and phase to log entries."""

    def test_basic_logging(self, caplog) -> None:
        caplog.set_level(logging.INFO)
        plog = PipelineLogger("test_logger", request_id="req-1", phase="plan")
        plog.info("Test message", task_count=5)

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.message == "Test message"
        assert record.request_id == "req-1"
        assert record.phase == "plan"
        assert record.task_count == 5

    def test_log_levels(self, caplog) -> None:
        caplog.set_level(logging.DEBUG)
        plog = PipelineLogger("test", request_id="r1")

        plog.debug("debug msg")
        plog.info("info msg")
        plog.warning("warning msg")
        plog.error("error msg")
        plog.critical("critical msg")

        levels = [r.levelname for r in caplog.records]
        assert levels == ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    def test_all_records_have_request_id(self, caplog) -> None:
        caplog.set_level(logging.INFO)
        plog = PipelineLogger("test", request_id="abc-123")
        plog.info("msg1")
        plog.info("msg2")

        for record in caplog.records:
            assert record.request_id == "abc-123"


class TestConfigureLogging:
    """configure_logging sets up the root logger correctly."""

    def test_default_config(self) -> None:
        configure_logging()
        root = logging.getLogger("no_slop_harness")
        assert root.level == logging.INFO
        assert len(root.handlers) > 0

    def test_json_output(self) -> None:
        configure_logging(level=logging.DEBUG, json_output=True)
        root = logging.getLogger("no_slop_harness")
        # Verify handler uses JSONFormatter by logging and checking output format
        # We check the formatter type
        handler = root.handlers[0]
        assert isinstance(handler.formatter, JSONFormatter)

    def test_quiets_noisy_loggers(self) -> None:
        configure_logging()
        assert logging.getLogger("urllib3").level == logging.WARNING
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("asyncio").level == logging.WARNING

    def test_reconfiguration_clears_handlers(self) -> None:
        configure_logging()
        first_handler_count = len(logging.getLogger("no_slop_harness").handlers)
        configure_logging()
        second_handler_count = len(logging.getLogger("no_slop_harness").handlers)
        assert first_handler_count == second_handler_count
