from __future__ import annotations

import asyncio
import sys
from typing import Generator

import pytest


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """跨平台事件循环。"""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
