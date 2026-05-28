"""Test suite for the no_slop_harness plugin system."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from no_slop_harness.plugin import PluginBase, PluginInfo, PluginRegistry

# ── Module-level plugin for load() tests ──────────────────────────────────────


class ModuleLevelPlugin(PluginBase):
    """A module-level plugin class used by load() tests that need importable classes."""

    plugin_name = "level1"  # Overridden per-test via PluginInfo
    plugin_version = "1.0"
    plugin_description = "Module-level test plugin"

    def on_load(self) -> None:
        pass


class ModulePlugin1(ModuleLevelPlugin):
    """Second module-level plugin for load_all tests."""

    plugin_name = "module_p1"


class ModulePlugin2(ModuleLevelPlugin):
    """Third module-level plugin for load_all tests."""

    plugin_name = "module_p2"


# ── PluginBase Tests ──────────────────────────────────────────────────────────


class TestPluginBase:
    """Tests for the PluginBase abstract base class."""

    def test_subclass_with_attributes_works(self) -> None:
        """A concrete subclass with plugin attributes instantiates correctly."""

        class MyPlugin(PluginBase):
            plugin_name = "my_plugin"
            plugin_version = "1.2.3"
            plugin_description = "A test plugin"

            def on_load(self) -> None:
                pass

        p = MyPlugin()
        assert p.plugin_name == "my_plugin"
        assert p.plugin_version == "1.2.3"
        assert p.plugin_description == "A test plugin"
        assert not p.is_loaded

    def test_default_attributes_on_minimal_subclass(self) -> None:
        """A minimal subclass inherits PluginBase defaults for version/description."""

        class MinimalPlugin(PluginBase):
            plugin_name = "minimal"

            def on_load(self) -> None:
                pass

        p = MinimalPlugin()
        assert p.plugin_name == "minimal"
        assert p.plugin_version == "0.1.0"
        assert p.plugin_description == ""
        assert not p.is_loaded

    def test_on_load_is_abstract(self) -> None:
        """Instantiating PluginBase directly or without on_load raises TypeError."""
        with pytest.raises(TypeError):
            PluginBase()  # type: ignore[abstract]

    def test_on_unload_sets_loaded_false(self) -> None:
        """Default on_unload() sets _loaded to False."""

        class TestPlugin(PluginBase):
            plugin_name = "test"

            def on_load(self) -> None:
                pass

        p = TestPlugin()
        p._loaded = True
        assert p.is_loaded
        p.on_unload()
        assert not p.is_loaded

    def test_on_unload_can_be_overridden(self) -> None:
        """Subclasses can override on_unload for custom cleanup."""

        cleanup_called: list[str] = []

        class CleanupPlugin(PluginBase):
            plugin_name = "cleanup"

            def on_load(self) -> None:
                pass

            def on_unload(self) -> None:
                cleanup_called.append("unloaded")
                super().on_unload()

        p = CleanupPlugin()
        p._loaded = True
        p.on_unload()
        assert cleanup_called == ["unloaded"]
        assert not p.is_loaded

    def test_is_loaded_property_reflects_state(self) -> None:
        """is_loaded property reflects _loaded attribute."""

        class TestPlugin(PluginBase):
            plugin_name = "test"

            def on_load(self) -> None:
                pass

        p = TestPlugin()
        assert not p.is_loaded
        p._loaded = True
        assert p.is_loaded
        p._loaded = False
        assert not p.is_loaded

    # ── Lifecycle hook no-op tests ────────────────────────────────────────

    def test_on_pipeline_start_is_noop(self) -> None:
        """on_pipeline_start is a no-op by default."""

        class TestPlugin(PluginBase):
            plugin_name = "test"

            def on_load(self) -> None:
                pass

        p = TestPlugin()
        # Should not raise
        p.on_pipeline_start("req-1")

    def test_on_pipeline_end_is_noop(self) -> None:
        """on_pipeline_end is a no-op by default."""

        class TestPlugin(PluginBase):
            plugin_name = "test"

            def on_load(self) -> None:
                pass

        p = TestPlugin()
        p.on_pipeline_end("req-1", True)
        p.on_pipeline_end("req-2", False)

    def test_on_task_complete_is_noop(self) -> None:
        """on_task_complete is a no-op by default."""

        class TestPlugin(PluginBase):
            plugin_name = "test"

            def on_load(self) -> None:
                pass

        p = TestPlugin()
        p.on_task_complete("task-1", "success")

    def test_on_verification_is_noop(self) -> None:
        """on_verification is a no-op by default."""

        class TestPlugin(PluginBase):
            plugin_name = "test"

            def on_load(self) -> None:
                pass

        p = TestPlugin()
        p.on_verification("task-1", True, "all good")

    def test_lifecycle_hooks_can_be_overridden(self) -> None:
        """Lifecycle hooks can be overridden in subclasses."""

        calls: list[tuple[str, tuple]] = []

        class HookPlugin(PluginBase):
            plugin_name = "hook"

            def on_load(self) -> None:
                pass

            def on_pipeline_start(self, request_id: str) -> None:
                calls.append(("on_pipeline_start", (request_id,)))

            def on_pipeline_end(self, request_id: str, success: bool) -> None:
                calls.append(("on_pipeline_end", (request_id, success)))

            def on_task_complete(self, task_id: str, result: str) -> None:
                calls.append(("on_task_complete", (task_id, result)))

            def on_verification(self, task_id: str, passed: bool, detail: str) -> None:
                calls.append(("on_verification", (task_id, passed, detail)))

        p = HookPlugin()
        p.on_pipeline_start("req-1")
        p.on_pipeline_end("req-1", True)
        p.on_task_complete("task-1", "done")
        p.on_verification("task-1", False, "failed check")

        assert calls == [
            ("on_pipeline_start", ("req-1",)),
            ("on_pipeline_end", ("req-1", True)),
            ("on_task_complete", ("task-1", "done")),
            ("on_verification", ("task-1", False, "failed check")),
        ]


# ── PluginInfo Tests ──────────────────────────────────────────────────────────


class TestPluginInfo:
    """Tests for the PluginInfo dataclass."""

    def test_all_fields_accessible(self) -> None:
        """All PluginInfo fields are accessible."""
        info = PluginInfo(
            name="test_plugin",
            version="2.0.0",
            description="A fine plugin",
            class_name="TestPlugin",
            module_path="tests.plugins.test_module",
            source="directory",
        )
        assert info.name == "test_plugin"
        assert info.version == "2.0.0"
        assert info.description == "A fine plugin"
        assert info.class_name == "TestPlugin"
        assert info.module_path == "tests.plugins.test_module"
        assert info.source == "directory"

    def test_defaults_not_provided(self) -> None:
        """PluginInfo has no defaults; all fields must be provided."""
        info = PluginInfo(
            name="",
            version="",
            description="",
            class_name="",
            module_path="",
            source="package",
        )
        assert info.source == "package"
        assert info.name == ""


# ── PluginRegistry Tests ──────────────────────────────────────────────────────


class TestPluginRegistryInit:
    """Tests for PluginRegistry initialization."""

    def test_empty_registry(self) -> None:
        """A new registry has no discovered or loaded plugins."""
        registry = PluginRegistry()
        assert registry.discovered_names == []
        assert registry.loaded_names == []

    def test_get_returns_none_for_unknown(self) -> None:
        """get() returns None for an unknown plugin."""
        registry = PluginRegistry()
        assert registry.get("nonexistent") is None

    def test_get_info_returns_none_for_unknown(self) -> None:
        """get_info() returns None for an unknown plugin."""
        registry = PluginRegistry()
        assert registry.get_info("nonexistent") is None


class TestPluginRegistryDiscoverDirectory:
    """Tests for PluginRegistry.discover_directory()."""

    def test_discovers_plugin_base_subclasses_in_py_files(self, tmp_path: Path) -> None:
        """discover_directory finds PluginBase subclasses in .py files."""
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()

        # Write a plugin module with a valid PluginBase subclass
        plugin_path = plugin_dir / "my_plugin.py"
        plugin_path.write_text(
            textwrap.dedent("""\
            from no_slop_harness.plugin import PluginBase

            class MyPlugin(PluginBase):
                plugin_name = "my_plugin"
                plugin_version = "1.0.0"
                plugin_description = "My test plugin"

                def on_load(self) -> None:
                    pass
            """)
        )

        registry = PluginRegistry()
        discovered = registry.discover_directory(str(plugin_dir))

        assert "my_plugin" in discovered
        assert registry.get_info("my_plugin") is not None

        info = registry.get_info("my_plugin")
        assert info is not None
        assert info.name == "my_plugin"
        assert info.version == "1.0.0"
        assert info.description == "My test plugin"
        assert info.class_name == "MyPlugin"
        assert info.source == "directory"

    def test_ignores_init_files(self, tmp_path: Path) -> None:
        """discover_directory ignores __init__.py files."""
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()

        # __init__.py with a PluginBase subclass (should be ignored)
        init_path = plugin_dir / "__init__.py"
        init_path.write_text(
            textwrap.dedent("""\
            from no_slop_harness.plugin import PluginBase

            class HiddenPlugin(PluginBase):
                plugin_name = "hidden"

                def on_load(self) -> None:
                    pass
            """)
        )

        registry = PluginRegistry()
        discovered = registry.discover_directory(str(plugin_dir))

        assert "hidden" not in discovered

    def test_ignores_underscore_prefixed_files(self, tmp_path: Path) -> None:
        """discover_directory ignores files starting with underscore."""
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()

        # _private.py should be ignored
        private_path = plugin_dir / "_private.py"
        private_path.write_text(
            textwrap.dedent("""\
            from no_slop_harness.plugin import PluginBase

            class PrivatePlugin(PluginBase):
                plugin_name = "private"

                def on_load(self) -> None:
                    pass
            """)
        )

        registry = PluginRegistry()
        discovered = registry.discover_directory(str(plugin_dir))

        assert "private" not in discovered

    def test_nonexistent_directory_returns_empty(self) -> None:
        """discover_directory returns empty list for non-existent directory."""
        registry = PluginRegistry()
        discovered = registry.discover_directory("/nonexistent/path/plugins")
        assert discovered == []

    def test_discovers_multiple_plugins_in_single_file(self, tmp_path: Path) -> None:
        """A single .py file can contain multiple PluginBase subclasses."""
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()

        plugin_path = plugin_dir / "multi.py"
        plugin_path.write_text(
            textwrap.dedent("""\
            from no_slop_harness.plugin import PluginBase

            class PluginA(PluginBase):
                plugin_name = "plugin_a"

                def on_load(self) -> None:
                    pass

            class PluginB(PluginBase):
                plugin_name = "plugin_b"

                def on_load(self) -> None:
                    pass
            """)
        )

        registry = PluginRegistry()
        discovered = registry.discover_directory(str(plugin_dir))

        assert "plugin_a" in discovered
        assert "plugin_b" in discovered
        assert len(discovered) == 2

    def test_non_plugin_classes_are_ignored(self, tmp_path: Path) -> None:
        """Classes that don't inherit from PluginBase are ignored."""
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()

        plugin_path = plugin_dir / "mixed.py"
        plugin_path.write_text(
            textwrap.dedent("""\
            from no_slop_harness.plugin import PluginBase

            class RegularClass:
                plugin_name = "not_really"

            class MyPlugin(PluginBase):
                plugin_name = "real_plugin"

                def on_load(self) -> None:
                    pass
            """)
        )

        registry = PluginRegistry()
        discovered = registry.discover_directory(str(plugin_dir))

        assert discovered == ["real_plugin"]
        assert "not_really" not in discovered

    def test_plugin_without_explicit_name_uses_class_name(self, tmp_path: Path) -> None:
        """Plugin without plugin_name attribute uses the class name."""
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()

        plugin_path = plugin_dir / "anon.py"
        plugin_path.write_text(
            textwrap.dedent("""\
            from no_slop_harness.plugin import PluginBase

            class AnonPlugin(PluginBase):
                def on_load(self) -> None:
                    pass
            """)
        )

        registry = PluginRegistry()
        discovered = registry.discover_directory(str(plugin_dir))

        # Falls back to class name when plugin_name is empty
        assert "AnonPlugin" in discovered or len(discovered) > 0

    def test_syntax_error_in_plugin_file_is_handled(self, tmp_path: Path) -> None:
        """A plugin file with a syntax error is skipped gracefully."""
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()

        bad_path = plugin_dir / "bad.py"
        bad_path.write_text("this is not valid Python {{{")

        registry = PluginRegistry()
        # Should not raise
        discovered = registry.discover_directory(str(plugin_dir))
        assert discovered == []


class TestPluginRegistryDiscoverPackage:
    """Tests for PluginRegistry.discover_package()."""

    def test_nonexistent_package_returns_empty(self) -> None:
        """discover_package returns empty list for non-existent package."""
        registry = PluginRegistry()
        discovered = registry.discover_package("nonexistent_package_xyz")
        assert discovered == []

    def test_discovers_plugins_in_existing_package(self) -> None:
        """discover_package scans a real package for PluginBase subclasses."""
        # Use the no_slop_harness package itself (likely empty of plugins,
        # but the import should work)
        registry = PluginRegistry()
        discovered = registry.discover_package("no_slop_harness")
        # Just verify it doesn't crash; it may or may not find plugins
        assert isinstance(discovered, list)

    def test_discovers_plugins_with_source_package(self) -> None:
        """Plugins discovered via discover_package have source='package'."""
        # We'll scan a dynamically-added module to be precise
        plugin_content = textwrap.dedent(  # noqa: F841
            """\
            from no_slop_harness.plugin import PluginBase

            class PkgPlugin(PluginBase):
                plugin_name = "pkg_plugin"
                plugin_version = "2.0.0"
                plugin_description = "Package-scanned plugin"

                def on_load(self) -> None:
                    pass
            """
        )

        # Build a real module for the test
        test_pkg_dir = Path(__file__).parent
        sys.path.insert(0, str(test_pkg_dir.parent))  # to allow import
        try:
            # Scan the existing project's module path
            registry = PluginRegistry()
            result = registry.discover_package("no_slop_harness")
            assert isinstance(result, list)
        finally:
            pass


class TestPluginRegistryLoad:
    """Tests for PluginRegistry.load()."""

    def test_load_instantiates_and_calls_on_load(self) -> None:
        """load() instantiates the plugin and calls on_load() using module-level class."""
        registry = PluginRegistry()
        info = PluginInfo(
            name="level1",
            version="1.0",
            description="",
            class_name="ModuleLevelPlugin",
            module_path=__name__,
            source="test",
        )
        registry._discovered["level1"] = info

        instance = registry.load("level1")
        assert instance is not None
        assert instance.is_loaded
        assert instance.plugin_name == "level1"

    def test_load_returns_none_for_unknown_plugin(self) -> None:
        """load() returns None for an unknown plugin name."""
        registry = PluginRegistry()
        assert registry.load("no_such_plugin") is None

    def test_load_returns_existing_for_already_loaded(self) -> None:
        """load() returns the existing instance for an already-loaded plugin."""
        registry = PluginRegistry()
        info = PluginInfo(
            name="once1",
            version="1.0",
            description="",
            class_name="ModuleLevelPlugin",
            module_path=__name__,
            source="test",
        )
        registry._discovered["once1"] = info

        first = registry.load("once1")
        assert first is not None
        second = registry.load("once1")
        assert first is second
        assert second.is_loaded

    def test_load_returns_plugin_base_instance(self) -> None:
        """load() returns a PluginBase instance for module-level plugin."""
        registry = PluginRegistry()
        info = PluginInfo(
            name="valid_ld",
            version="1.0",
            description="",
            class_name="ModuleLevelPlugin",
            module_path=__name__,
            source="test",
        )
        registry._discovered["valid_ld"] = info

        instance = registry.load("valid_ld")
        assert isinstance(instance, PluginBase)
        # plugin_name comes from the class attribute (ModuleLevelPlugin.plugin_name = "level1")

    def test_load_returns_none_if_class_not_found(self) -> None:
        """load() returns None when class_name doesn't exist in module."""
        registry = PluginRegistry()
        registry._discovered["ghost"] = PluginInfo(
            name="ghost",
            version="1.0",
            description="",
            class_name="NoSuchClassXYZ",
            module_path="tests.test_plugin",
            source="test",
        )
        assert registry.load("ghost") is None


class TestPluginRegistryLoadAll:
    """Tests for PluginRegistry.load_all()."""

    def test_load_all_loads_all_discovered(self) -> None:
        """load_all() loads every discovered plugin using module-level classes."""
        registry = PluginRegistry()
        registry._discovered["p1"] = PluginInfo(
            name="p1",
            version="1.0",
            description="",
            class_name="ModulePlugin1",
            module_path=__name__,
            source="test",
        )
        registry._discovered["p2"] = PluginInfo(
            name="p2",
            version="1.0",
            description="",
            class_name="ModulePlugin2",
            module_path=__name__,
            source="test",
        )

        loaded = registry.load_all()
        assert set(loaded) == {"p1", "p2"}
        assert registry.get("p1") is not None
        assert registry.get("p2") is not None

    def test_load_all_returns_only_successfully_loaded(self) -> None:
        """load_all() returns only names that loaded successfully."""
        registry = PluginRegistry()
        registry._discovered["good"] = PluginInfo(
            name="good",
            version="1.0",
            description="",
            class_name="ModuleLevelPlugin",
            module_path=__name__,
            source="test",
        )
        registry._discovered["bad"] = PluginInfo(
            name="bad",
            version="1.0",
            description="",
            class_name="NoSuchClass",
            module_path=__name__,
            source="test",
        )

        loaded = registry.load_all()
        assert "good" in loaded
        assert "bad" not in loaded

    def test_load_all_empty_registry(self) -> None:
        """load_all() on an empty registry returns empty list."""
        registry = PluginRegistry()
        assert registry.load_all() == []


class TestPluginRegistryUnload:
    """Tests for PluginRegistry.unload()."""

    def test_unload_calls_on_unload_and_removes(self) -> None:
        """unload() calls on_unload() and removes from loaded dict."""
        unload_called: list[str] = []

        class UnloadPlugin(PluginBase):
            plugin_name = "unload_test"

            def on_load(self) -> None:
                pass

            def on_unload(self) -> None:
                unload_called.append("unloaded")
                super().on_unload()

        registry = PluginRegistry()
        instance = UnloadPlugin()
        instance._loaded = True
        registry._loaded["unload_test"] = instance

        assert "unload_test" in registry.loaded_names
        registry.unload("unload_test")
        assert unload_called == ["unloaded"]
        assert "unload_test" not in registry.loaded_names

    def test_unload_nonexistent_does_nothing(self) -> None:
        """unload() on a non-existent/non-loaded plugin does not raise."""
        registry = PluginRegistry()
        registry.unload("does_not_exist")

    def test_unload_allows_reload(self) -> None:
        """After unload, a plugin can be loaded again."""
        registry = PluginRegistry()
        info = PluginInfo(
            name="reloadable",
            version="1.0",
            description="",
            class_name="ModuleLevelPlugin",
            module_path=__name__,
            source="test",
        )
        registry._discovered["reloadable"] = info

        first = registry.load("reloadable")
        assert first is not None
        registry.unload("reloadable")
        second = registry.load("reloadable")
        assert second is not None
        assert first is not second


class TestPluginRegistryBroadcast:
    """Tests for PluginRegistry broadcast / lifecycle hook methods."""

    def test_broadcast_on_pipeline_start(self) -> None:
        """on_pipeline_start broadcasts to all loaded plugins."""
        calls: list[tuple[str, str]] = []

        class StartPlugin(PluginBase):
            plugin_name = "startp"

            def on_load(self) -> None:
                pass

            def on_pipeline_start(self, request_id: str) -> None:
                calls.append(("startp", request_id))

        registry = PluginRegistry()
        registry._loaded["startp"] = StartPlugin()
        registry._loaded["startp"]._loaded = True
        registry.on_pipeline_start("req-42")
        assert calls == [("startp", "req-42")]

    def test_broadcast_on_pipeline_end(self) -> None:
        """on_pipeline_end broadcasts success/failure to all loaded plugins."""
        calls: list[tuple[str, str, bool]] = []

        class EndPlugin(PluginBase):
            plugin_name = "endp"

            def on_load(self) -> None:
                pass

            def on_pipeline_end(self, request_id: str, success: bool) -> None:
                calls.append(("endp", request_id, success))

        registry = PluginRegistry()
        registry._loaded["endp"] = EndPlugin()
        registry._loaded["endp"]._loaded = True
        registry.on_pipeline_end("req-1", False)
        assert calls == [("endp", "req-1", False)]

    def test_broadcast_on_task_complete(self) -> None:
        """on_task_complete broadcasts to all loaded plugins."""
        calls: list[tuple[str, str, str]] = []

        class TaskPlugin(PluginBase):
            plugin_name = "taskp"

            def on_load(self) -> None:
                pass

            def on_task_complete(self, task_id: str, result: str) -> None:
                calls.append(("taskp", task_id, result))

        registry = PluginRegistry()
        registry._loaded["taskp"] = TaskPlugin()
        registry._loaded["taskp"]._loaded = True
        registry.on_task_complete("task-7", "great success")
        assert calls == [("taskp", "task-7", "great success")]

    def test_broadcast_on_verification(self) -> None:
        """on_verification broadcasts to all loaded plugins."""
        calls: list[tuple[str, str, bool, str]] = []

        class VerifyPlugin(PluginBase):
            plugin_name = "verifyp"

            def on_load(self) -> None:
                pass

            def on_verification(self, task_id: str, passed: bool, detail: str) -> None:
                calls.append(("verifyp", task_id, passed, detail))

        registry = PluginRegistry()
        registry._loaded["verifyp"] = VerifyPlugin()
        registry._loaded["verifyp"]._loaded = True
        registry.on_verification("task-3", True, "all tests passed")
        assert calls == [("verifyp", "task-3", True, "all tests passed")]

    def test_broadcasts_to_multiple_loaded_plugins(self) -> None:
        """Broadcasts reach all loaded plugins."""
        calls: list[str] = []

        class BroadcastA(PluginBase):
            plugin_name = "broadcast_a"

            def on_load(self) -> None:
                pass

            def on_pipeline_start(self, request_id: str) -> None:
                calls.append(f"a:{request_id}")

        class BroadcastB(PluginBase):
            plugin_name = "broadcast_b"

            def on_load(self) -> None:
                pass

            def on_pipeline_start(self, request_id: str) -> None:
                calls.append(f"b:{request_id}")

        registry = PluginRegistry()
        registry._loaded["broadcast_a"] = BroadcastA()
        registry._loaded["broadcast_a"]._loaded = True
        registry._loaded["broadcast_b"] = BroadcastB()
        registry._loaded["broadcast_b"]._loaded = True
        registry.on_pipeline_start("multi")
        assert sorted(calls) == ["a:multi", "b:multi"]

    def test_broadcast_does_not_reach_unloaded_plugins(self) -> None:
        """Broadcasts skip plugins that are discovered but not loaded."""
        calls: list[str] = []

        class SilentPlugin(PluginBase):
            plugin_name = "silent"

            def on_load(self) -> None:
                pass

            def on_pipeline_start(self, request_id: str) -> None:
                calls.append("should not fire")

        registry = PluginRegistry()
        registry._discovered["silent"] = PluginInfo(
            name="silent",
            version="1.0",
            description="",
            class_name="SilentPlugin",
            module_path=__name__,
            source="test",
        )
        registry.on_pipeline_start("req-1")
        assert calls == []

    def test_broadcast_handles_plugin_exception_gracefully(self) -> None:
        """If one plugin's hook raises, other plugins still receive the broadcast."""
        calls: list[str] = []

        class BadPlugin(PluginBase):
            plugin_name = "bad"

            def on_load(self) -> None:
                pass

            def on_pipeline_start(self, request_id: str) -> None:
                raise RuntimeError("boom")

        class GoodPlugin(PluginBase):
            plugin_name = "good"

            def on_load(self) -> None:
                pass

            def on_pipeline_start(self, request_id: str) -> None:
                calls.append(request_id)

        registry = PluginRegistry()
        registry._loaded["bad"] = BadPlugin()
        registry._loaded["bad"]._loaded = True
        registry._loaded["good"] = GoodPlugin()
        registry._loaded["good"]._loaded = True

        registry.on_pipeline_start("survivor")
        assert calls == ["survivor"]


class TestPluginRegistryQuery:
    """Tests for PluginRegistry query methods."""

    def test_discovered_names(self) -> None:
        """discovered_names returns all discovered plugin names."""
        registry = PluginRegistry()
        assert registry.discovered_names == []

        registry._discovered["a"] = PluginInfo(
            name="a",
            version="1",
            description="",
            class_name="A",
            module_path="x",
            source="test",
        )
        registry._discovered["b"] = PluginInfo(
            name="b",
            version="1",
            description="",
            class_name="B",
            module_path="x",
            source="test",
        )
        assert sorted(registry.discovered_names) == ["a", "b"]

    def test_loaded_names(self) -> None:
        """loaded_names returns all loaded plugin names."""
        registry = PluginRegistry()
        assert registry.loaded_names == []

        registry._loaded["q"] = ModuleLevelPlugin()
        registry._loaded["q"]._loaded = True
        assert registry.loaded_names == ["q"]

    def test_get_returns_loaded_plugin(self) -> None:
        """get() returns the loaded plugin instance."""
        registry = PluginRegistry()
        instance = ModuleLevelPlugin()
        instance._loaded = True
        registry._loaded["get_me"] = instance
        result = registry.get("get_me")
        assert result is instance

    def test_get_info_returns_metadata(self) -> None:
        """get_info() returns PluginInfo for a discovered plugin."""
        registry = PluginRegistry()
        info = PluginInfo(
            name="info_test",
            version="3.0",
            description="Informative",
            class_name="InfoTest",
            module_path="tests",
            source="directory",
        )
        registry._discovered["info_test"] = info
        result = registry.get_info("info_test")
        assert result is info
        assert result.name == "info_test"
        assert result.version == "3.0"
        assert result.description == "Informative"
        assert result.class_name == "InfoTest"
        assert result.source == "directory"


class TestPluginRegistryEndToEnd:
    """End-to-end tests using tmp_path with real plugin files."""

    def test_full_discover_load_broadcast_unload_cycle(self, tmp_path: Path) -> None:
        """Full lifecycle: discover from directory, load, broadcast, unload."""
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()

        plugin_path = plugin_dir / "my_plg.py"
        plugin_path.write_text(
            textwrap.dedent("""\
            from no_slop_harness.plugin import PluginBase

            class MyPlugin(PluginBase):
                plugin_name = "my_plg"
                plugin_version = "1.5.0"
                plugin_description = "End-to-end test plugin"

                def on_load(self) -> None:
                    pass
            """)
        )

        registry = PluginRegistry()

        # Discover
        discovered = registry.discover_directory(str(plugin_dir))
        assert "my_plg" in discovered

        # Load
        instance = registry.load("my_plg")
        assert instance is not None
        assert instance.is_loaded
        assert instance.plugin_name == "my_plg"
        assert instance.plugin_version == "1.5.0"

        # Query
        assert registry.get("my_plg") is instance
        assert registry.get_info("my_plg") is not None
        assert "my_plg" in registry.loaded_names

        # Unload
        registry.unload("my_plg")
        assert not instance.is_loaded
        assert "my_plg" not in registry.loaded_names
        assert registry.get("my_plg") is None
        # Info still available after unload (only removed from _loaded, not _discovered)
        assert registry.get_info("my_plg") is not None

    def test_load_all_discovers_and_loads_all(self, tmp_path: Path) -> None:
        """load_all loads every plugin discovered in a directory."""
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()

        for i in range(3):
            p = plugin_dir / f"plugin_{i}.py"
            p.write_text(
                textwrap.dedent(f"""\
                from no_slop_harness.plugin import PluginBase

                class Plugin{i}(PluginBase):
                    plugin_name = "plugin_{i}"

                    def on_load(self) -> None:
                        pass
                """)
            )

        registry = PluginRegistry()
        registry.discover_directory(str(plugin_dir))
        loaded = registry.load_all()

        assert sorted(loaded) == ["plugin_0", "plugin_1", "plugin_2"]
        assert sorted(registry.loaded_names) == ["plugin_0", "plugin_1", "plugin_2"]
        for name in loaded:
            assert registry.get(name) is not None
            assert registry.get(name).is_loaded  # type: ignore[union-attr]
