"""Agent factory for clink CLI integrations.

Provides builtin agent implementations and dynamic loading of custom agents
from user-provided Python modules.
"""

from __future__ import annotations

import logging
from pathlib import Path

from clink.models import ResolvedCLIClient

from .base import AgentOutput, BaseCLIAgent, CLIAgentError
from .claude import ClaudeAgent
from .codex import CodexAgent
from .gemini import GeminiAgent

logger = logging.getLogger("clink.agents")

# Registry of builtin agent classes
_AGENTS: dict[str, type[BaseCLIAgent]] = {
    "gemini": GeminiAgent,
    "codex": CodexAgent,
    "claude": ClaudeAgent,
}


def create_agent(client: ResolvedCLIClient) -> BaseCLIAgent:
    """Create an agent using legacy name-based lookup (backward compatible)."""
    agent_key = (client.runner or client.name).lower()
    agent_cls = _AGENTS.get(agent_key, BaseCLIAgent)
    return agent_cls(client)


def create_agent_from_spec(
    client: ResolvedCLIClient,
    runner_spec: str | None = None,
    *,
    config_base_dir: Path | None = None,
) -> BaseCLIAgent:
    """
    Create an agent from a specification string.

    Supports:
      - None: Use BaseCLIAgent (generic runner)
      - Builtin names (legacy): "gemini", "codex", "claude"
      - Builtin prefix: "builtin:gemini"
      - Custom path: "~/.pal/agents/my_agent.py:MyAgent"

    Custom agents must inherit from BaseCLIAgent and can import from clink.agents.base:
        from clink.agents.base import BaseCLIAgent, AgentOutput, CLIAgentError

    Args:
        client: The resolved CLI client configuration
        runner_spec: Agent specification string (uses client.runner if None)
        config_base_dir: Base directory for resolving relative paths

    Returns:
        Instantiated agent
    """
    # Use client's runner spec if not explicitly provided
    spec = runner_spec if runner_spec is not None else client.runner

    # None means use BaseCLIAgent
    if spec is None:
        logger.debug("No runner spec for '%s', using BaseCLIAgent", client.name)
        return BaseCLIAgent(client)

    # Use config_base_dir from client if not explicitly provided
    if config_base_dir is None:
        config_base_dir = client.config_base_dir

    from clink.loader import LoaderError, load_class_from_spec, normalize_spec

    # Normalize the spec (add builtin: prefix for plain names)
    normalized = normalize_spec(spec, _AGENTS)

    try:
        agent_cls = load_class_from_spec(
            normalized,
            BaseCLIAgent,
            _AGENTS,
            config_base_dir=config_base_dir,
        )
        return agent_cls(client)
    except LoaderError as exc:
        # Log warning but fall back to BaseCLIAgent for robustness
        logger.warning(
            "Failed to load agent from spec '%s' for CLI '%s': %s. Falling back to BaseCLIAgent.",
            spec,
            client.name,
            exc,
        )
        return BaseCLIAgent(client)


def list_builtin_agents() -> list[str]:
    """Return a sorted list of builtin agent names."""
    return sorted(_AGENTS.keys())


__all__ = [
    "AgentOutput",
    "BaseCLIAgent",
    "CLIAgentError",
    "create_agent",
    "create_agent_from_spec",
    "list_builtin_agents",
]
