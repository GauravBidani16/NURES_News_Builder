"""Unit tests for TaskManager active task tracking and cancellation."""

import asyncio

import pytest

from news_post_builder.core.task_manager import TaskManager


@pytest.mark.asyncio
async def test_task_manager_register_and_cancel() -> None:
    tm = TaskManager()
    started = asyncio.Event()
    cancelled = False

    async def sample_work() -> None:
        nonlocal cancelled
        started.set()
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            cancelled = True
            raise

    task = asyncio.create_task(sample_work())
    await started.wait()
    tm.register("session-123", task)

    # Cancel the task
    assert tm.cancel("session-123") is True
    with pytest.raises(asyncio.CancelledError):
        await task

    assert cancelled is True
    assert tm.cancel("session-123") is False


@pytest.mark.asyncio
async def test_task_manager_unregister() -> None:
    tm = TaskManager()
    task = asyncio.create_task(asyncio.sleep(0.1))
    tm.register("s-1", task)
    tm.unregister("s-1")
    assert tm.cancel("s-1") is False
    await task
