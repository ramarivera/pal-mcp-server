"""Parser for Cursor Agent CLI stream-json (NDJSON) output."""

from __future__ import annotations

import json
from typing import Any

from .base import BaseParser, ParsedCLIResponse, ParserError


class CursorNDJSONParser(BaseParser):
    """Parse stdout from `cursor-agent -p --output-format stream-json`.

    The cursor-agent CLI emits newline-delimited JSON (NDJSON) events:
    - system/init: Session initialization with model, cwd, session_id
    - user: User prompt message
    - assistant: Complete assistant message segments
    - tool_call/started: Tool execution begins
    - tool_call/completed: Tool execution with result
    - result/success: Terminal event with aggregated result text
    """

    name = "cursor_ndjson"

    def parse(self, stdout: str, stderr: str) -> ParsedCLIResponse:
        lines = [line.strip() for line in (stdout or "").splitlines() if line.strip()]
        events: list[dict[str, Any]] = []
        assistant_messages: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        terminal_result: dict[str, Any] | None = None
        session_id: str | None = None

        for line in lines:
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            events.append(event)
            event_type = event.get("type")
            subtype = event.get("subtype")

            if not session_id:
                session_id = event.get("session_id")

            if event_type == "assistant":
                msg = event.get("message", {})
                content = msg.get("content", [])
                for content_block in content:
                    if content_block.get("type") == "text":
                        text = content_block.get("text", "").strip()
                        if text:
                            assistant_messages.append(text)

            elif event_type == "tool_call":
                tool_calls.append(event)

            elif event_type == "result" and subtype == "success":
                terminal_result = event

        # Prefer terminal result's aggregated text
        content = ""
        if terminal_result:
            content = terminal_result.get("result", "").strip()

        # Fall back to joining assistant messages if no terminal result
        if not content and assistant_messages:
            content = "\n\n".join(assistant_messages)

        if not content:
            # Check for error in stderr
            stderr_text = (stderr or "").strip()
            if stderr_text:
                raise ParserError(f"Cursor CLI returned no result. stderr: {stderr_text}")
            raise ParserError("Cursor CLI stream-json output did not contain a result")

        metadata: dict[str, Any] = {"events": events}

        if terminal_result:
            if terminal_result.get("duration_ms") is not None:
                metadata["duration_ms"] = terminal_result.get("duration_ms")
            if terminal_result.get("duration_api_ms") is not None:
                metadata["duration_api_ms"] = terminal_result.get("duration_api_ms")
            if terminal_result.get("request_id"):
                metadata["request_id"] = terminal_result.get("request_id")
            metadata["is_error"] = terminal_result.get("is_error", False)

        if session_id:
            metadata["session_id"] = session_id

        if tool_calls:
            metadata["tool_calls"] = tool_calls
            metadata["tool_call_count"] = len([tc for tc in tool_calls if tc.get("subtype") == "completed"])

        stderr_text = (stderr or "").strip()
        if stderr_text:
            metadata["stderr"] = stderr_text

        return ParsedCLIResponse(content=content, metadata=metadata)
