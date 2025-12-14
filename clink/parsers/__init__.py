"""Parser registry for clink.

Provides builtin parsers and dynamic loading of custom parsers from user-provided
Python modules.
"""

from __future__ import annotations

from pathlib import Path

from .base import BaseParser, ParsedCLIResponse, ParserError
from .claude import ClaudeJSONParser
from .codex import CodexJSONLParser
from .gemini import GeminiJSONParser

# Registry of builtin parser classes
_PARSER_CLASSES: dict[str, type[BaseParser]] = {
    CodexJSONLParser.name: CodexJSONLParser,
    GeminiJSONParser.name: GeminiJSONParser,
    ClaudeJSONParser.name: ClaudeJSONParser,
}


def get_parser(name: str) -> BaseParser:
    """Get a builtin parser by name (legacy interface)."""
    normalized = (name or "").lower()
    if normalized not in _PARSER_CLASSES:
        raise ParserError(f"No parser registered for '{name}'")
    parser_cls = _PARSER_CLASSES[normalized]
    return parser_cls()


def get_parser_from_spec(
    spec: str,
    *,
    config_base_dir: Path | None = None,
) -> BaseParser:
    """
    Get a parser instance from a specification string.

    Supports:
      - Builtin names (legacy): "gemini_json", "claude_json", "codex_jsonl"
      - Builtin prefix: "builtin:gemini_json"
      - Custom path: "~/.pal/parsers/my_parser.py:MyParser"

    Custom parsers must inherit from BaseParser and can import from clink.parsers.base:
        from clink.parsers.base import BaseParser, ParsedCLIResponse

    Args:
        spec: Parser specification string
        config_base_dir: Base directory for resolving relative paths in custom specs

    Returns:
        Instantiated parser

    Raises:
        ParserError: If the parser cannot be loaded
    """
    from clink.loader import LoaderError, load_class_from_spec, normalize_spec

    if not spec:
        raise ParserError("Parser spec cannot be empty")

    # Normalize the spec (add builtin: prefix for plain names)
    normalized = normalize_spec(spec, _PARSER_CLASSES)

    try:
        parser_cls = load_class_from_spec(
            normalized,
            BaseParser,
            _PARSER_CLASSES,
            config_base_dir=config_base_dir,
        )
        return parser_cls()
    except LoaderError as exc:
        raise ParserError(str(exc)) from exc


def list_builtin_parsers() -> list[str]:
    """Return a sorted list of builtin parser names."""
    return sorted(_PARSER_CLASSES.keys())


__all__ = [
    "BaseParser",
    "ParsedCLIResponse",
    "ParserError",
    "get_parser",
    "get_parser_from_spec",
    "list_builtin_parsers",
]
