from __future__ import annotations

import time

import echotools


def test_import_core_is_fast() -> None:
  start = time.perf_counter()
  import importlib

  importlib.reload(echotools)
  elapsed_ms = (time.perf_counter() - start) * 1000
  assert elapsed_ms < 500, f"import echotools took {elapsed_ms:.1f}ms"
