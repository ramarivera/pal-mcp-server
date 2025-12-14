"""Dynamic class loading utilities for clink custom CLIs.

This module provides utilities to load parser and agent classes from specification
strings, enabling config-only custom CLI support without code changes.

Spec formats:
  - "builtin:<name>" - Look up in a builtin registry
  - "path/to/module.py:ClassName" - Dynamic import from file
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import TypeVar

logger = logging.getLogger("clink.loader")

T = TypeVar("T")


class LoaderError(RuntimeError):
    """Raised when dynamic class loading fails."""


def load_class_from_spec(
    spec: str,
    base_class: type[T],
    builtin_registry: dict[str, type[T]],
    *,
    config_base_dir: Path | None = None,
) -> type[T]:
    """
    Load a class from a specification string.

    Supports two formats:
      - "builtin:<name>" - Look up in builtin_registry
      - "path/to/module.py:ClassName" - Dynamic import from file

    Custom modules can import from pal-mcp-server packages, e.g.:
        from clink.parsers.base import BaseParser, ParsedCLIResponse

    Args:
        spec: The specification string
        base_class: Expected base class for validation
        builtin_registry: Dict mapping builtin names to classes
        config_base_dir: Base directory for resolving relative paths

    Returns:
        The loaded class (not an instance)

    Raises:
        LoaderError: If loading fails for any reason
    """
    if not spec or not isinstance(spec, str):
        raise LoaderError(f"Invalid spec: {spec!r} (must be a non-empty string)")

    spec = spec.strip()

    # Handle builtin: prefix
    if spec.startswith("builtin:"):
        name = spec[len("builtin:") :]
        return _load_builtin(name, builtin_registry)

    # Handle path:ClassName format
    if ":" in spec:
        return _load_from_path(spec, base_class, config_base_dir)

    # Legacy support: treat plain names as builtin (no prefix)
    # This maintains backward compatibility with existing configs
    if spec in builtin_registry:
        logger.debug("Treating plain name '%s' as builtin (legacy support)", spec)
        return builtin_registry[spec]

    # If it looks like a path (contains / or \), try loading from path
    if "/" in spec or "\\" in spec:
        raise LoaderError(f"Invalid spec '{spec}'. Path specs must include class name: 'path/to/module.py:ClassName'")

    # Unknown format
    available = ", ".join(sorted(builtin_registry.keys()))
    raise LoaderError(
        f"Unknown spec '{spec}'. Use 'builtin:<name>' or 'path:ClassName'. " f"Available builtins: {available}"
    )


def _load_builtin(name: str, registry: dict[str, type[T]]) -> type[T]:
    """Load a class from the builtin registry."""
    # Normalize name (lowercase, strip whitespace)
    normalized = name.strip().lower()

    if not normalized:
        raise LoaderError("Empty builtin name")

    if normalized not in registry:
        available = ", ".join(sorted(registry.keys()))
        raise LoaderError(f"Unknown builtin '{name}'. Available: {available}")

    return registry[normalized]


def _load_from_path(
    spec: str,
    base_class: type[T],
    config_base_dir: Path | None,
) -> type[T]:
    """Load a class from a Python file path."""
    # Parse path:ClassName format
    if ":" not in spec:
        raise LoaderError(f"Invalid path spec '{spec}'. Expected 'path/to/module.py:ClassName'")

    # Split on the last colon to handle Windows paths like C:\path\file.py:Class
    path_str, class_name = spec.rsplit(":", 1)
    class_name = class_name.strip()

    if not class_name:
        raise LoaderError(f"Missing class name in spec '{spec}'")

    if not path_str:
        raise LoaderError(f"Missing path in spec '{spec}'")

    # Resolve the path
    path = Path(path_str).expanduser()

    if not path.is_absolute():
        if config_base_dir:
            path = (config_base_dir / path).resolve()
        else:
            path = path.resolve()

    # Validate the path
    if not path.exists():
        raise LoaderError(f"Module file not found: {path}")

    if not path.is_file():
        raise LoaderError(f"Not a file: {path}")

    if path.suffix.lower() != ".py":
        raise LoaderError(f"Module must be a .py file: {path}")

    # Dynamic import
    module = _import_module_from_path(path)

    # Get the class
    if not hasattr(module, class_name):
        # List available classes that inherit from base_class
        available_classes = [
            name
            for name, obj in vars(module).items()
            if isinstance(obj, type) and issubclass(obj, base_class) and obj is not base_class
        ]
        hint = f" Available: {', '.join(available_classes)}" if available_classes else ""
        raise LoaderError(f"Class '{class_name}' not found in {path}.{hint}")

    cls = getattr(module, class_name)

    # Validate it's a class
    if not isinstance(cls, type):
        raise LoaderError(f"'{class_name}' in {path} is not a class (got {type(cls).__name__})")

    # Validate inheritance
    if not issubclass(cls, base_class):
        raise LoaderError(
            f"'{class_name}' must inherit from {base_class.__name__}, "
            f"but inherits from {', '.join(b.__name__ for b in cls.__bases__)}"
        )

    logger.info("Loaded custom class %s from %s", class_name, path)
    return cls


def _import_module_from_path(path: Path):
    """Dynamically import a Python module from a file path."""
    # Create a unique module name to avoid collisions
    # Use path hash to ensure same path always gets same module name
    module_name = f"clink_custom_{path.stem}_{hash(str(path.resolve())) & 0xFFFFFFFF:08x}"

    # Check if already imported
    if module_name in sys.modules:
        logger.debug("Reusing cached module %s from %s", module_name, path)
        return sys.modules[module_name]

    try:
        spec_obj = importlib.util.spec_from_file_location(module_name, path)
        if spec_obj is None:
            raise LoaderError(f"Failed to create import spec for {path}")
        if spec_obj.loader is None:
            raise LoaderError(f"No loader available for {path}")

        module = importlib.util.module_from_spec(spec_obj)
        sys.modules[module_name] = module

        try:
            spec_obj.loader.exec_module(module)
        except Exception as exc:
            # Clean up on failure
            sys.modules.pop(module_name, None)
            raise LoaderError(f"Error executing module {path}: {exc}") from exc

        return module

    except LoaderError:
        raise
    except Exception as exc:
        raise LoaderError(f"Failed to import module {path}: {exc}") from exc


def normalize_spec(spec: str, builtin_registry: dict[str, type]) -> str:
    """
    Normalize a spec string, adding 'builtin:' prefix if needed.

    This provides backward compatibility for plain builtin names.

    Args:
        spec: The spec string to normalize
        builtin_registry: Registry to check for plain names

    Returns:
        Normalized spec string
    """
    if not spec:
        return spec

    spec = spec.strip()

    # Already has a prefix or is a path spec
    if ":" in spec or "/" in spec or "\\" in spec:
        return spec

    # Plain name that exists in registry -> add builtin prefix
    if spec.lower() in builtin_registry:
        return f"builtin:{spec}"

    return spec
