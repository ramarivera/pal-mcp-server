"""X.AI (GROK) model provider implementation."""

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from tools.models import ToolModelCategory

from .openai_compatible import OpenAICompatibleProvider
from .shared import ModelCapabilities, ProviderType
from .xai_registry import XAIModelRegistry

logger = logging.getLogger(__name__)


class XAIModelProvider(OpenAICompatibleProvider):
    """Integration for X.AI's GROK models exposed over an OpenAI-style API.

    Publishes capability metadata for the officially supported deployments and
    maps tool-category preferences to the appropriate GROK model.
    """

    FRIENDLY_NAME = "X.AI"

    MODEL_CAPABILITIES: dict[str, ModelCapabilities] = {}
    _registry: Optional[XAIModelRegistry] = None

    def __init__(self, api_key: str, **kwargs):
        """Initialize X.AI provider with API key."""
        # Set X.AI base URL
        kwargs.setdefault("base_url", "https://api.x.ai/v1")
        self._ensure_registry()
        super().__init__(api_key, **kwargs)
        self._invalidate_capability_cache()

    # ------------------------------------------------------------------
    # Registry access
    # ------------------------------------------------------------------

    @classmethod
    def _ensure_registry(cls, *, force_reload: bool = False) -> None:
        """Load capability registry into MODEL_CAPABILITIES."""

        if cls._registry is not None and not force_reload:
            return

        try:
            registry = XAIModelRegistry()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Unable to load X.AI model registry: %s", exc)
            cls._registry = None
            cls.MODEL_CAPABILITIES = {}
            return

        cls._registry = registry
        cls.MODEL_CAPABILITIES = dict(registry.model_map)

    @classmethod
    def reload_registry(cls) -> None:
        """Force registry reload (primarily for tests)."""

        cls._ensure_registry(force_reload=True)

    def get_all_model_capabilities(self) -> dict[str, ModelCapabilities]:
        self._ensure_registry()
        return super().get_all_model_capabilities()

    def get_model_registry(self) -> Optional[dict[str, ModelCapabilities]]:
        if self._registry is None:
            return None
        return dict(self._registry.model_map)

    def get_provider_type(self) -> ProviderType:
        """Get the provider type."""
        return ProviderType.XAI

    def get_preferred_model(self, category: "ToolModelCategory", allowed_models: list[str]) -> Optional[str]:
        """Get XAI's preferred model for a given category from allowed models.

        Args:
            category: The tool category requiring a model
            allowed_models: Pre-filtered list of models allowed by restrictions

        Returns:
            Preferred model name or None
        """
        from tools.models import ToolModelCategory

        if not allowed_models:
            return None

        if category == ToolModelCategory.EXTENDED_REASONING:
            # Prefer GROK-4 for advanced reasoning with thinking mode
            if "grok-4" in allowed_models:
                return "grok-4"
            elif "grok-3" in allowed_models:
                return "grok-3"
            # Fall back to any available model
            return allowed_models[0]

        elif category == ToolModelCategory.FAST_RESPONSE:
            # Prefer GROK-3-Fast for speed, then GROK-4
            if "grok-3-fast" in allowed_models:
                return "grok-3-fast"
            elif "grok-4" in allowed_models:
                return "grok-4"
            # Fall back to any available model
            return allowed_models[0]

        else:  # BALANCED or default
            # Prefer GROK-4 for balanced use (best overall capabilities)
            if "grok-4" in allowed_models:
                return "grok-4"
            elif "grok-3" in allowed_models:
                return "grok-3"
            elif "grok-3-fast" in allowed_models:
                return "grok-3-fast"
            # Fall back to any available model
            return allowed_models[0]


# Load registry data at import time
XAIModelProvider._ensure_registry()
