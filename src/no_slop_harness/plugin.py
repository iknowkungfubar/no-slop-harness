"""Plugin system for the No-Slop Harness.

Provides plugin discovery, registration, and lifecycle management
for extending the framework with custom providers, tools, verifiers,
and pipeline hooks.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

logger = logging.getLogger(__name__)


# ── Plugin Interface ────────────────────────────────────────────────────────


class PluginBase(ABC):
    """Base class for all No-Slop Harness plugins.

    Plugins must implement `on_load()` and may override lifecycle hooks.
    Each plugin class attribute `plugin_name` uniquely identifies it.
    """

    # Subclasses must override:
    plugin_name: str = ""
    plugin_version: str = "0.1.0"
    plugin_description: str = ""

    def __init__(self) -> None:
        self._loaded = False

    @abstractmethod
    def on_load(self) -> None:
        """Called when the plugin is loaded. Register hooks here."""
        ...

    def on_unload(self) -> None:
        """Called when the plugin is unloaded. Clean up resources."""
        self._loaded = False

    def on_pipeline_start(self, request_id: str) -> None:  # noqa: B027
        """Hook called when a pipeline starts.

        Args:
            request_id: The pipeline request ID.
        """

    def on_pipeline_end(self, request_id: str, success: bool) -> None:  # noqa: B027
        """Hook called when a pipeline ends.

        Args:
            request_id: The pipeline request ID.
            success: Whether the pipeline completed successfully.
        """

    def on_task_complete(self, task_id: str, result: str) -> None:  # noqa: B027
        """Hook called when a task completes.

        Args:
            task_id: The task identifier.
            result: The task result string.
        """

    def on_verification(self, task_id: str, passed: bool, detail: str) -> None:  # noqa: B027
        """Hook called after verification.

        Args:
            task_id: The task identifier.
            passed: Whether verification passed.
            detail: Verification detail string.
        """

    @property
    def is_loaded(self) -> bool:
        """Whether the plugin is currently loaded."""
        return self._loaded


# ── Plugin Registry ──────────────────────────────────────────────────────────


@dataclass
class PluginInfo:
    """Metadata for a discovered plugin."""

    name: str
    version: str
    description: str
    class_name: str
    module_path: str
    source: str  # "directory" or "package"


class PluginRegistry:
    """Central registry for discovering, loading, and managing plugins.

    Usage:
        registry = PluginRegistry()
        registry.discover_directory("/path/to/plugins")
        registry.discover_package("my_plugins_package")
        registry.load_all()
        registry.on_pipeline_start("abc-123")
    """

    def __init__(self) -> None:
        self._discovered: dict[str, PluginInfo] = {}
        self._loaded: dict[str, PluginBase] = {}

    # ── Discovery ────────────────────────────────────────────────────────

    def discover_directory(self, directory: str | Path) -> list[str]:
        """Discover plugins in a directory of Python module files.

        Each .py file in the directory (except __init__.py) is scanned
        for classes inheriting from PluginBase.

        Args:
            directory: Path to the plugins directory.

        Returns:
            List of discovered plugin names.
        """
        dir_path = Path(directory).resolve()
        if not dir_path.is_dir():
            logger.warning("Plugin directory not found: %s", dir_path)
            return []

        discovered: list[str] = []

        for py_file in sorted(dir_path.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(py_file.stem, str(py_file))
                if spec is None or spec.loader is None:
                    logger.warning("Could not load spec for plugin file: %s", py_file)
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[py_file.stem] = module
                spec.loader.exec_module(module)
                found = self._scan_module(module, source="directory")
                discovered.extend(found)
            except Exception as e:
                logger.warning("Error loading plugin module %s: %s", py_file.stem, e)

        return discovered

    def discover_package(self, package_name: str) -> list[str]:
        """Discover plugins in an installed Python package.

        The package must expose a `get_plugins()` function returning
        a list of PluginBase subclasses, or have them importable directly.

        Args:
            package_name: The package name (e.g., "no_slop_contrib").

        Returns:
            List of discovered plugin names.
        """
        try:
            module = importlib.import_module(package_name)
        except ImportError:
            logger.warning("Plugin package not found: %s", package_name)
            return []

        found = self._scan_module(module, source="package")
        return found

    def _scan_module(self, module: ModuleType, source: str) -> list[str]:
        """Scan a module for PluginBase subclasses."""
        discovered: list[str] = []
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, PluginBase) or obj is PluginBase:
                continue
            plugin_name = getattr(obj, "plugin_name", "") or name
            info = PluginInfo(
                name=plugin_name,
                version=getattr(obj, "plugin_version", "0.1.0"),
                description=getattr(obj, "plugin_description", ""),
                class_name=name,
                module_path=module.__name__,
                source=source,
            )
            self._discovered[plugin_name] = info
            discovered.append(plugin_name)
            logger.debug("Discovered plugin: %s (v%s) from %s", plugin_name, info.version, source)
        return discovered

    # ── Loading ──────────────────────────────────────────────────────────

    def load(self, name: str) -> PluginBase | None:
        """Load a single plugin by name.

        Args:
            name: The plugin name.

        Returns:
            The loaded plugin instance, or None if not found or already loaded.
        """
        if name in self._loaded:
            logger.debug("Plugin already loaded: %s", name)
            return self._loaded[name]

        info = self._discovered.get(name)
        if info is None:
            logger.warning("Plugin not found: %s", name)
            return None

        try:
            module = importlib.import_module(info.module_path)
            plugin_class = getattr(module, info.class_name)
            instance = plugin_class()
            instance.on_load()
            instance._loaded = True
            self._loaded[name] = instance
            logger.info("Loaded plugin: %s v%s", name, info.version)
            return instance  # type: ignore[no-any-return]
        except Exception as e:
            logger.error("Failed to load plugin %s: %s", name, e)
            return None

    def load_all(self) -> list[str]:
        """Load all discovered plugins.

        Returns:
            List of successfully loaded plugin names.
        """
        loaded: list[str] = []
        for name in self._discovered:
            if self.load(name) is not None:
                loaded.append(name)
        return loaded

    def unload(self, name: str) -> None:
        """Unload a plugin by name.

        Args:
            name: The plugin name.
        """
        plugin = self._loaded.pop(name, None)
        if plugin is not None:
            plugin.on_unload()
            logger.info("Unloaded plugin: %s", name)

    # ── Lifecycle Hooks ──────────────────────────────────────────────────

    def _broadcast(self, method: str, *args: Any, **kwargs: Any) -> None:
        """Broadcast a lifecycle event to all loaded plugins."""
        for name, plugin in self._loaded.items():
            try:
                getattr(plugin, method)(*args, **kwargs)
            except Exception as e:
                logger.error("Plugin %s.%s error: %s", name, method, e)

    def on_pipeline_start(self, request_id: str) -> None:
        """Notify all plugins that a pipeline has started."""
        self._broadcast("on_pipeline_start", request_id)

    def on_pipeline_end(self, request_id: str, success: bool) -> None:
        """Notify all plugins that a pipeline has ended."""
        self._broadcast("on_pipeline_end", request_id, success)

    def on_task_complete(self, task_id: str, result: str) -> None:
        """Notify all plugins that a task has completed."""
        self._broadcast("on_task_complete", task_id, result)

    def on_verification(self, task_id: str, passed: bool, detail: str) -> None:
        """Notify all plugins of a verification result."""
        self._broadcast("on_verification", task_id, passed, detail)

    # ── Query ────────────────────────────────────────────────────────────

    @property
    def discovered_names(self) -> list[str]:
        """Names of all discovered plugins."""
        return list(self._discovered.keys())

    @property
    def loaded_names(self) -> list[str]:
        """Names of all loaded plugins."""
        return list(self._loaded.keys())

    def get(self, name: str) -> PluginBase | None:
        """Get a loaded plugin by name."""
        return self._loaded.get(name)

    def get_info(self, name: str) -> PluginInfo | None:
        """Get metadata for a plugin by name."""
        return self._discovered.get(name)
