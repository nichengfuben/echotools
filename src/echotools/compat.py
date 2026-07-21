from __future__ import annotations

"""Backward-compatible import aliases for pre-2.3.9 module paths."""

import importlib
import importlib.abc
import importlib.util
import sys
from types import ModuleType
from typing import Dict, Optional, Sequence

_MODULE_ALIASES: Dict[str, str] = {
    "echotools.cache": "echotools.base.cache",
    "echotools.config": "echotools.base.config",
    "echotools.dispatch": "echotools.exec.dispatch",
    "echotools.files": "echotools.plat.files",
    "echotools.fncall": "echotools.exec.fncall",
    "echotools.ids": "echotools.base.ids",
    "echotools.io": "echotools.base.io",
    "echotools.lifecycle": "echotools.exec.lifecycle",
    "echotools.logger": "echotools.base.logger",
    "echotools.plugin": "echotools.plat.plugin",
    "echotools.process": "echotools.exec.process",
    "echotools.protocol": "echotools.exec.protocol",
    "echotools.proxy": "echotools.plat.proxy",
    "echotools.retry": "echotools.base.retry",
    "echotools.scheduler": "echotools.plat.scheduler",
    "echotools.terminal": "echotools.exec.terminal",
    "echotools.web": "echotools.media.web",
    "echotools.events": "echotools.media.events",
    "echotools.spinner": "echotools.media.spinner",
    "echotools.tracing": "echotools.media.tracing",
    "echotools.translate": "echotools.media.translate",
    "echotools.watcher": "echotools.media.watcher",
    "echotools.network": "echotools.plat.network",
    "echotools.runtime": "echotools.plat.runtime",
    "echotools.sdk": "echotools.plat.sdk",
    "echotools.keys": "echotools.exec.keys",
}


def _map_name(fullname: str) -> Optional[str]:
    for old, new in _MODULE_ALIASES.items():
        if fullname == old or fullname.startswith(old + "."):
            return new + fullname[len(old) :]
    return None


class _AliasLoader(importlib.abc.Loader):
    def __init__(self, fullname: str, target: str) -> None:
        self._fullname = fullname
        self._target = target

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> Optional[ModuleType]:
        return None

    def exec_module(self, module: ModuleType) -> None:
        target = importlib.import_module(self._target)
        module.__dict__.update(target.__dict__)
        module.__name__ = self._fullname
        module.__package__ = self._fullname.rpartition(".")[0]
        sys.modules[self._fullname] = module


class _AliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(
        self,
        fullname: str,
        path: Optional[Sequence[str]],
        target: Optional[ModuleType] = None,
    ) -> Optional[importlib.machinery.ModuleSpec]:
        mapped = _map_name(fullname)
        if mapped is None:
            return None
        return importlib.util.spec_from_loader(
            fullname,
            _AliasLoader(fullname, mapped),
        )


def install_compat_aliases() -> None:
    if not any(isinstance(finder, _AliasFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _AliasFinder())
