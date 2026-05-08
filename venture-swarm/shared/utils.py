from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx

from shared.logging_config import get_logger, setup_logging


@dataclass(frozen=True)
class TimedResult:
    latency_s: float
    value: Any


@asynccontextmanager
async def http_client(timeout_s: float = 8.0) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s)) as client:
        yield client


async def sleep_jitter(base_s: float, jitter_s: float = 0.25) -> None:
    await asyncio.sleep(base_s + (jitter_s * (time.monotonic() % 1.0)))


async def timed(coro) -> TimedResult:
    start = time.perf_counter()
    value = await coro
    return TimedResult(latency_s=time.perf_counter() - start, value=value)


__all__ = ["setup_logging", "get_logger", "TimedResult", "http_client", "sleep_jitter", "timed"]
