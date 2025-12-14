"""Tests for the OpenCode CLI JSON parser."""

import pytest

from clink.parsers.base import ParserError
from clink.parsers.opencode import OpenCodeJSONParser


def _build_simple_response() -> str:
    """Build a simple NDJSON response with step_start, text, and step_finish."""
    return "\n".join(
        [
            '{"type":"step_start","timestamp":1765680022322,"sessionID":"ses_abc123","part":{"id":"prt_1","sessionID":"ses_abc123","messageID":"msg_1","type":"step-start","snapshot":"abc123"}}',
            '{"type":"text","timestamp":1765680022322,"sessionID":"ses_abc123","part":{"id":"prt_2","sessionID":"ses_abc123","messageID":"msg_1","type":"text","text":"Hello, world!","time":{"start":1765680022321,"end":1765680022321}}}',
            '{"type":"step_finish","timestamp":1765680022385,"sessionID":"ses_abc123","part":{"id":"prt_3","sessionID":"ses_abc123","messageID":"msg_1","type":"step-finish","reason":"stop","snapshot":"abc123","cost":0.001,"tokens":{"input":10,"output":5,"reasoning":0,"cache":{"read":0,"write":100}}}}',
        ]
    )


def _build_multi_text_response() -> str:
    """Build a response with multiple text events."""
    return "\n".join(
        [
            '{"type":"step_start","timestamp":1765680022322,"sessionID":"ses_abc123","part":{}}',
            '{"type":"text","timestamp":1765680022322,"sessionID":"ses_abc123","part":{"text":"First part."}}',
            '{"type":"text","timestamp":1765680022323,"sessionID":"ses_abc123","part":{"text":"Second part."}}',
            '{"type":"text","timestamp":1765680022324,"sessionID":"ses_abc123","part":{"text":"Third part."}}',
            '{"type":"step_finish","timestamp":1765680022385,"sessionID":"ses_abc123","part":{"reason":"stop","tokens":{"input":20,"output":15}}}',
        ]
    )


def _build_tool_use_response() -> str:
    """Build a response with tool use events."""
    return "\n".join(
        [
            '{"type":"step_start","sessionID":"ses_abc123","part":{}}',
            '{"type":"text","sessionID":"ses_abc123","part":{"text":"Let me check that file."}}',
            '{"type":"tool_use","sessionID":"ses_abc123","part":{"tool":"read_file","input":{"path":"test.py"}}}',
            '{"type":"tool_result","sessionID":"ses_abc123","part":{"tool":"read_file","output":"file contents"}}',
            '{"type":"text","sessionID":"ses_abc123","part":{"text":"Here is the result."}}',
            '{"type":"step_finish","sessionID":"ses_abc123","part":{"reason":"stop","tokens":{"input":50,"output":30}}}',
        ]
    )


class TestOpenCodeJSONParser:
    """Tests for OpenCodeJSONParser."""

    def test_parser_name(self):
        parser = OpenCodeJSONParser()
        assert parser.name == "opencode_json"

    def test_extracts_text_content(self):
        parser = OpenCodeJSONParser()
        stdout = _build_simple_response()

        parsed = parser.parse(stdout=stdout, stderr="")

        assert parsed.content == "Hello, world!"

    def test_extracts_session_id(self):
        parser = OpenCodeJSONParser()
        stdout = _build_simple_response()

        parsed = parser.parse(stdout=stdout, stderr="")

        assert parsed.metadata["session_id"] == "ses_abc123"

    def test_extracts_token_counts(self):
        parser = OpenCodeJSONParser()
        stdout = _build_simple_response()

        parsed = parser.parse(stdout=stdout, stderr="")

        assert parsed.metadata["input_tokens"] == 10
        assert parsed.metadata["output_tokens"] == 5
        assert parsed.metadata["reasoning_tokens"] == 0
        assert parsed.metadata["cache_read"] == 0
        assert parsed.metadata["cache_write"] == 100

    def test_extracts_cost(self):
        parser = OpenCodeJSONParser()
        stdout = _build_simple_response()

        parsed = parser.parse(stdout=stdout, stderr="")

        assert parsed.metadata["cost"] == 0.001

    def test_extracts_finish_reason(self):
        parser = OpenCodeJSONParser()
        stdout = _build_simple_response()

        parsed = parser.parse(stdout=stdout, stderr="")

        assert parsed.metadata["finish_reason"] == "stop"

    def test_combines_multiple_text_parts(self):
        parser = OpenCodeJSONParser()
        stdout = _build_multi_text_response()

        parsed = parser.parse(stdout=stdout, stderr="")

        assert parsed.content == "First part.\n\nSecond part.\n\nThird part."

    def test_tracks_tool_events(self):
        parser = OpenCodeJSONParser()
        stdout = _build_tool_use_response()

        parsed = parser.parse(stdout=stdout, stderr="")

        assert "tool_events" in parsed.metadata
        assert parsed.metadata["tool_call_count"] == 1
        assert parsed.content == "Let me check that file.\n\nHere is the result."

    def test_captures_stderr(self):
        parser = OpenCodeJSONParser()
        stdout = _build_simple_response()

        parsed = parser.parse(stdout=stdout, stderr="debug info")

        assert parsed.metadata["stderr"] == "debug info"

    def test_stores_raw_events(self):
        parser = OpenCodeJSONParser()
        stdout = _build_simple_response()

        parsed = parser.parse(stdout=stdout, stderr="")

        assert "events" in parsed.metadata
        assert len(parsed.metadata["events"]) == 3

    def test_raises_on_empty_output(self):
        parser = OpenCodeJSONParser()

        with pytest.raises(ParserError) as exc_info:
            parser.parse(stdout="", stderr="")

        assert "did not contain any text response" in str(exc_info.value)

    def test_raises_with_stderr_on_empty_output(self):
        parser = OpenCodeJSONParser()

        with pytest.raises(ParserError) as exc_info:
            parser.parse(stdout="", stderr="Error: API key invalid")

        assert "API key invalid" in str(exc_info.value)

    def test_ignores_non_json_lines(self):
        parser = OpenCodeJSONParser()
        stdout = "\n".join(
            [
                "Some debug output",
                '{"type":"text","sessionID":"ses_abc123","part":{"text":"Hello"}}',
                "More debug",
                '{"type":"step_finish","sessionID":"ses_abc123","part":{"reason":"stop"}}',
            ]
        )

        parsed = parser.parse(stdout=stdout, stderr="")

        assert parsed.content == "Hello"

    def test_handles_malformed_json_gracefully(self):
        parser = OpenCodeJSONParser()
        stdout = "\n".join(
            [
                '{"type":"text","sessionID":"ses_abc123","part":{"text":"Hello"}}',
                '{"broken json',
                '{"type":"step_finish","sessionID":"ses_abc123","part":{"reason":"stop"}}',
            ]
        )

        parsed = parser.parse(stdout=stdout, stderr="")

        assert parsed.content == "Hello"
