"""Core package namespace compatibility for legacy imports.

The project is historically imported via both ``core.*`` (legacy flat name) and
``src.core.*`` (source-tree name).  This package ensures that both names resolve
to the **same** module objects so that classes, functions and singletons keep a
single identity regardless of which import path a test or worker uses first.
"""

import importlib
import importlib.util
import sys
import types
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec

_module = sys.modules[__name__]

# Mutual top-level package alias.
if __name__ == "core":
    sys.modules.setdefault("src.core", _module)
elif __name__ == "src.core":
    sys.modules.setdefault("core", _module)


class _AliasLoader(Loader):
    """Return an already-loaded canonical module for the legacy name."""

    def __init__(self, canonical_module: types.ModuleType) -> None:
        self._canonical_module = canonical_module

    def create_module(self, spec: ModuleSpec) -> types.ModuleType:
        return self._canonical_module

    def exec_module(self, module: types.ModuleType) -> None:
        pass


class _RedirectLoader(Loader):
    """Load the canonical ``src.core.*`` module and alias it to ``core.*``."""

    def __init__(
        self,
        legacy_name: str,
        canonical_name: str,
        real_loader: Loader | None,
    ) -> None:
        self._legacy_name = legacy_name
        self._canonical_name = canonical_name
        self._real_loader = real_loader

    def create_module(self, spec: ModuleSpec) -> types.ModuleType | None:
        # Defer to default module creation; we replace the entry in exec_module.
        return None

    def exec_module(self, module: types.ModuleType) -> None:
        if self._canonical_name not in sys.modules:
            importlib.import_module(self._canonical_name)
        canonical_mod = sys.modules[self._canonical_name]
        sys.modules[self._legacy_name] = canonical_mod


class _SrcCoreAliasFinder(MetaPathFinder):
    """Redirect legacy ``core.*`` imports to the canonical ``src.core.*`` tree."""

    LEGACY_PREFIX = "core."
    CANONICAL_PREFIX = "src.core."

    def find_spec(
        self,
        fullname: str,
        path: object = None,
        target: object = None,
    ) -> ModuleSpec | None:
        if fullname == "core":
            canonical = "src.core"
        elif fullname.startswith(self.LEGACY_PREFIX):
            canonical = self.CANONICAL_PREFIX + fullname[len(self.LEGACY_PREFIX) :]
        else:
            return None

        # Already loaded under the canonical name -> return an alias spec.
        if canonical in sys.modules:
            return ModuleSpec(fullname, _AliasLoader(sys.modules[canonical]))

        spec = importlib.util.find_spec(canonical)
        if spec is None:
            return None
        alias_spec = ModuleSpec(
            fullname,
            _RedirectLoader(fullname, canonical, spec.loader),
            origin=spec.origin,
            loader_state=spec.loader_state,
            is_package=spec.submodule_search_locations is not None,
        )
        if spec.submodule_search_locations is not None:
            alias_spec.submodule_search_locations = spec.submodule_search_locations
        return alias_spec


# Install exactly once, at the front, so it can short-circuit legacy imports.
if not any(isinstance(finder, _SrcCoreAliasFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _SrcCoreAliasFinder())
