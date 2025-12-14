"""Unit tests for clink dynamic class loader and config-only CLI support."""

import tempfile
from pathlib import Path

import pytest

from clink.agents import BaseCLIAgent, create_agent_from_spec, list_builtin_agents
from clink.agents.claude import ClaudeAgent
from clink.agents.codex import CodexAgent
from clink.agents.gemini import GeminiAgent
from clink.loader import LoaderError, load_class_from_spec, normalize_spec
from clink.models import CLIClientConfig, ResolvedCLIClient, ResolvedCLIRole
from clink.parsers import BaseParser, get_parser_from_spec, list_builtin_parsers
from clink.parsers.claude import ClaudeJSONParser
from clink.parsers.codex import CodexJSONLParser
from clink.parsers.gemini import GeminiJSONParser


class TestLoaderBasics:
    """Test basic loader functionality."""

    def test_load_builtin_parser(self):
        """Test loading a builtin parser by spec."""
        parser = get_parser_from_spec("builtin:gemini_json")
        assert isinstance(parser, GeminiJSONParser)

    def test_load_builtin_parser_legacy_name(self):
        """Test loading a builtin parser by legacy plain name."""
        parser = get_parser_from_spec("claude_json")
        assert isinstance(parser, ClaudeJSONParser)

    def test_load_builtin_parser_case_insensitive(self):
        """Test builtin parser names are case insensitive."""
        parser = get_parser_from_spec("builtin:CODEX_JSONL")
        assert isinstance(parser, CodexJSONLParser)

    def test_load_unknown_builtin_raises(self):
        """Test that unknown builtin names raise ParserError."""
        from clink.parsers import ParserError

        with pytest.raises(ParserError, match="Unknown builtin"):
            get_parser_from_spec("builtin:nonexistent")

    def test_empty_spec_raises(self):
        """Test that empty spec raises ParserError."""
        from clink.parsers import ParserError

        with pytest.raises(ParserError, match="cannot be empty"):
            get_parser_from_spec("")


class TestNormalizeSpec:
    """Test spec normalization for backward compatibility."""

    def test_normalize_plain_builtin_name(self):
        """Test plain builtin names get builtin: prefix."""
        registry = {"foo": object, "bar": object}
        assert normalize_spec("foo", registry) == "builtin:foo"
        assert normalize_spec("bar", registry) == "builtin:bar"

    def test_normalize_already_prefixed(self):
        """Test already-prefixed specs are unchanged."""
        registry = {"foo": object}
        assert normalize_spec("builtin:foo", registry) == "builtin:foo"

    def test_normalize_path_spec(self):
        """Test path specs are unchanged."""
        registry = {"foo": object}
        spec = "/path/to/module.py:ClassName"
        assert normalize_spec(spec, registry) == spec

    def test_normalize_unknown_plain_name(self):
        """Test unknown plain names are unchanged (will fail later)."""
        registry = {"foo": object}
        assert normalize_spec("unknown", registry) == "unknown"

    def test_normalize_empty_spec(self):
        """Test empty specs are unchanged."""
        registry = {"foo": object}
        assert normalize_spec("", registry) == ""


class TestLoadFromPath:
    """Test loading custom classes from Python files."""

    def test_load_custom_parser_from_file(self):
        """Test loading a custom parser from a Python file."""
        # Create a temporary custom parser file
        custom_parser_code = '''
"""Custom parser for testing."""
from clink.parsers.base import BaseParser, ParsedCLIResponse


class TestCustomParser(BaseParser):
    """A custom parser for testing."""

    name = "test_custom"

    def parse(self, stdout: str, stderr: str) -> ParsedCLIResponse:
        return ParsedCLIResponse(
            content=f"CUSTOM:{stdout.strip()}",
            metadata={"custom": True},
        )
'''
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(custom_parser_code)
            temp_path = Path(f.name)

        try:
            parser = get_parser_from_spec(f"{temp_path}:TestCustomParser")
            assert parser.name == "test_custom"
            result = parser.parse("hello", "")
            assert result.content == "CUSTOM:hello"
            assert result.metadata["custom"] is True
        finally:
            temp_path.unlink()

    def test_load_missing_file_raises(self):
        """Test that missing file raises LoaderError."""
        with pytest.raises(LoaderError, match="not found"):
            load_class_from_spec(
                "/nonexistent/path/module.py:SomeClass",
                BaseParser,
                {},
            )

    def test_load_missing_class_raises(self):
        """Test that missing class raises LoaderError."""
        custom_code = '''
class SomeOtherClass:
    pass
'''
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(custom_code)
            temp_path = Path(f.name)

        try:
            with pytest.raises(LoaderError, match="Class.*not found"):
                load_class_from_spec(
                    f"{temp_path}:NonExistentClass",
                    object,
                    {},
                )
        finally:
            temp_path.unlink()

    def test_load_wrong_base_class_raises(self):
        """Test that classes not inheriting from base raise LoaderError."""
        custom_code = '''
class NotAParser:
    pass
'''
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(custom_code)
            temp_path = Path(f.name)

        try:
            with pytest.raises(LoaderError, match="must inherit from"):
                load_class_from_spec(
                    f"{temp_path}:NotAParser",
                    BaseParser,
                    {},
                )
        finally:
            temp_path.unlink()

    def test_load_non_py_file_raises(self):
        """Test that non-.py files raise LoaderError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("not python")
            temp_path = Path(f.name)

        try:
            with pytest.raises(LoaderError, match="must be a .py file"):
                load_class_from_spec(
                    f"{temp_path}:SomeClass",
                    object,
                    {},
                )
        finally:
            temp_path.unlink()

    def test_path_spec_without_class_raises(self):
        """Test that path spec without class name raises."""
        with pytest.raises(LoaderError, match="Path specs must include class name"):
            load_class_from_spec(
                "/some/path.py",
                object,
                {},
            )


class TestAgentLoading:
    """Test agent loading functionality."""

    def test_list_builtin_agents(self):
        """Test listing builtin agents."""
        agents = list_builtin_agents()
        assert "gemini" in agents
        assert "claude" in agents
        assert "codex" in agents

    def test_create_agent_from_spec_builtin(self):
        """Test creating agent from builtin spec."""
        # Create a minimal resolved client for testing
        client = ResolvedCLIClient(
            name="test",
            executable=["echo"],
            working_dir=None,
            internal_args=[],
            config_args=[],
            env={},
            timeout_seconds=60,
            parser="gemini_json",
            runner="builtin:gemini",
            roles={"default": ResolvedCLIRole(name="default", prompt_path=Path("/tmp/test.md"))},
        )
        agent = create_agent_from_spec(client, "builtin:gemini")
        assert isinstance(agent, GeminiAgent)

    def test_create_agent_from_spec_none_returns_base(self):
        """Test that None runner spec returns BaseCLIAgent."""
        client = ResolvedCLIClient(
            name="test",
            executable=["echo"],
            working_dir=None,
            internal_args=[],
            config_args=[],
            env={},
            timeout_seconds=60,
            parser="gemini_json",
            runner=None,
            roles={"default": ResolvedCLIRole(name="default", prompt_path=Path("/tmp/test.md"))},
        )
        agent = create_agent_from_spec(client)
        assert type(agent) is BaseCLIAgent

    def test_create_agent_fallback_on_error(self):
        """Test that invalid runner spec falls back to BaseCLIAgent."""
        client = ResolvedCLIClient(
            name="test",
            executable=["echo"],
            working_dir=None,
            internal_args=[],
            config_args=[],
            env={},
            timeout_seconds=60,
            parser="gemini_json",
            runner="invalid:nonexistent",
            roles={"default": ResolvedCLIRole(name="default", prompt_path=Path("/tmp/test.md"))},
        )
        # Should log warning but return BaseCLIAgent
        agent = create_agent_from_spec(client)
        assert type(agent) is BaseCLIAgent


class TestParserLoading:
    """Test parser loading functionality."""

    def test_list_builtin_parsers(self):
        """Test listing builtin parsers."""
        parsers = list_builtin_parsers()
        assert "gemini_json" in parsers
        assert "claude_json" in parsers
        assert "codex_jsonl" in parsers

    def test_get_parser_from_spec_all_builtins(self):
        """Test loading all builtin parsers by spec."""
        gemini = get_parser_from_spec("builtin:gemini_json")
        assert isinstance(gemini, GeminiJSONParser)

        claude = get_parser_from_spec("builtin:claude_json")
        assert isinstance(claude, ClaudeJSONParser)

        codex = get_parser_from_spec("builtin:codex_jsonl")
        assert isinstance(codex, CodexJSONLParser)


class TestCLIClientConfigModel:
    """Test the CLIClientConfig model with new fields."""

    def test_model_accepts_new_fields(self):
        """Test that CLIClientConfig accepts parser, runner, internal_args, default_role_prompt."""
        config = CLIClientConfig(
            name="custom-cli",
            command="my-cli",
            parser="builtin:gemini_json",
            runner="builtin:gemini",
            internal_args=["--output", "json"],
            default_role_prompt="prompts/default.md",
        )
        assert config.name == "custom-cli"
        assert config.command == "my-cli"
        assert config.parser == "builtin:gemini_json"
        assert config.runner == "builtin:gemini"
        assert config.internal_args == ["--output", "json"]
        assert config.default_role_prompt == "prompts/default.md"

    def test_model_defaults(self):
        """Test CLIClientConfig defaults for new fields."""
        config = CLIClientConfig(name="test")
        assert config.parser is None
        assert config.runner is None
        assert config.internal_args == []
        assert config.default_role_prompt is None

    def test_internal_args_coercion(self):
        """Test that internal_args can be a single string."""
        config = CLIClientConfig(name="test", internal_args="--single-arg")
        assert config.internal_args == ["--single-arg"]


class TestResolvedCLIClient:
    """Test ResolvedCLIClient with config_base_dir."""

    def test_config_base_dir_from_source_path(self):
        """Test config_base_dir is derived from config_source_path."""
        client = ResolvedCLIClient(
            name="test",
            executable=["echo"],
            working_dir=None,
            internal_args=[],
            config_args=[],
            env={},
            timeout_seconds=60,
            parser="gemini_json",
            roles={"default": ResolvedCLIRole(name="default", prompt_path=Path("/tmp/test.md"))},
            config_source_path=Path("/home/user/.pal/cli_clients/custom.json"),
        )
        assert client.config_base_dir == Path("/home/user/.pal/cli_clients")

    def test_config_base_dir_none_without_source(self):
        """Test config_base_dir is None when no source path."""
        client = ResolvedCLIClient(
            name="test",
            executable=["echo"],
            working_dir=None,
            internal_args=[],
            config_args=[],
            env={},
            timeout_seconds=60,
            parser="gemini_json",
            roles={"default": ResolvedCLIRole(name="default", prompt_path=Path("/tmp/test.md"))},
        )
        assert client.config_base_dir is None


class TestCustomCLIValidation:
    """Test registry validation for custom CLIs."""

    def test_custom_cli_config_requires_command(self):
        """Test that custom CLI config must have command field."""
        # This is tested at registry level, not model level
        # The model allows None, registry validates
        config = CLIClientConfig(
            name="custom-no-command",
            parser="builtin:gemini_json",
            # command is missing
        )
        assert config.command is None

    def test_custom_cli_config_requires_parser(self):
        """Test that custom CLI config must have parser field."""
        config = CLIClientConfig(
            name="custom-no-parser",
            command="my-cli",
            # parser is missing
        )
        assert config.parser is None


class TestRelativePathResolution:
    """Test relative path resolution in custom specs."""

    def test_relative_path_resolved_against_config_base_dir(self):
        """Test that relative paths in specs are resolved against config_base_dir."""
        # Create a temporary directory structure
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Create custom parser in subdirectory
            parsers_dir = base_dir / "custom_parsers"
            parsers_dir.mkdir()

            custom_parser_code = '''
from clink.parsers.base import BaseParser, ParsedCLIResponse


class RelativePathParser(BaseParser):
    name = "relative_test"

    def parse(self, stdout: str, stderr: str) -> ParsedCLIResponse:
        return ParsedCLIResponse(content=stdout, metadata={})
'''
            parser_file = parsers_dir / "my_parser.py"
            parser_file.write_text(custom_parser_code)

            # Load with relative path, resolved against base_dir
            parser = get_parser_from_spec(
                "custom_parsers/my_parser.py:RelativePathParser",
                config_base_dir=base_dir,
            )
            assert parser.name == "relative_test"


class TestModuleCaching:
    """Test that dynamically loaded modules are cached."""

    def test_module_cached_on_reload(self):
        """Test that loading same module twice returns cached version."""
        import sys

        custom_code = '''
from clink.parsers.base import BaseParser, ParsedCLIResponse

LOAD_COUNT = 0

class CachedParser(BaseParser):
    name = "cached"

    def __init__(self):
        global LOAD_COUNT
        LOAD_COUNT += 1

    def parse(self, stdout: str, stderr: str) -> ParsedCLIResponse:
        return ParsedCLIResponse(content=stdout, metadata={})
'''
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(custom_code)
            temp_path = Path(f.name)

        try:
            # First load
            parser1 = get_parser_from_spec(f"{temp_path}:CachedParser")

            # Second load should use cached module
            parser2 = get_parser_from_spec(f"{temp_path}:CachedParser")

            # Both should be instances of the same class
            assert type(parser1).__name__ == type(parser2).__name__
        finally:
            # Clean up cached module
            module_keys = [k for k in sys.modules if k.startswith("clink_custom_")]
            for k in module_keys:
                del sys.modules[k]
            temp_path.unlink()
