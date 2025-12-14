"""Parser for OpenCode CLI JSON output (NDJSON format)."""

from __future__ import annotations

import json
from typing import Any

from .base import BaseParser, ParsedCLIResponse, ParserError


class OpenCodeJSONParser(BaseParser):
    """Parse stdout from `opencode run --format json`.

    The opencode CLI emits newline-delimited JSON (NDJSON) events:
    - step_start: Marks the beginning of a processing step
    - text: Text content from the assistant
    - tool_use: Tool call initiated
    - tool_result: Tool call result
    - step_finish: Terminal event with tokens, cost, and completion reason
    """

    name = "opencode_json"

    def parse(self, stdout: str, stderr: str) -> ParsedCLIResponse:
        lines = [line.strip() for line in (stdout or "").splitlines() if line.strip()]
        events: list[dict[str, Any]] = []
        text_parts: list[str] = []
        tool_events: list[dict[str, Any]] = []
        step_finish: dict[str, Any] | None = None
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

            if not session_id:
                session_id = event.get("sessionID")

            if event_type == "text":
                part = event.get("part", {})
                text = part.get("text", "").strip()
                if text:
                    text_parts.append(text)

            elif event_type in ("tool_use", "tool_result"):
                tool_events.append(event)

            elif event_type == "step_finish":
                step_finish = event

        # Combine all text parts
        content = "\n\n".join(text_parts) if text_parts else ""

        if not content:
            stderr_text = (stderr or "").strip()
            if stderr_text:
                raise ParserError(f"OpenCode CLI returned no result. stderr: {stderr_text}")
            raise ParserError("OpenCode CLI JSON output did not contain any text response")

        metadata: dict[str, Any] = {"events": events}

        if step_finish:
            part = step_finish.get("part", {})
            tokens = part.get("tokens", {})
            if tokens:
                metadata["tokens"] = tokens
                metadata["input_tokens"] = tokens.get("input", 0)
                metadata["output_tokens"] = tokens.get("output", 0)
                metadata["reasoning_tokens"] = tokens.get("reasoning", 0)
                cache = tokens.get("cache", {})
                if cache:
                    metadata["cache_read"] = cache.get("read", 0)
                    metadata["cache_write"] = cache.get("write", 0)

            if part.get("cost") is not None:
                metadata["cost"] = part.get("cost")

            if part.get("reason"):
                metadata["finish_reason"] = part.get("reason")

        if session_id:
            metadata["session_id"] = session_id

        if tool_events:
            metadata["tool_events"] = tool_events
            metadata["tool_call_count"] = len([e for e in tool_events if e.get("type") == "tool_result"])

        stderr_text = (stderr or "").strip()
        if stderr_text:
            metadata["stderr"] = stderr_text

        return ParsedCLIResponse(content=content, metadata=metadata)
