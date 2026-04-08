"""account_lock 모듈 테스트 — 계좌 단위 직렬화 검증."""

import asyncio
from uuid import uuid4

import pytest

from app.services.account_lock import (
    clear_account_lock,
    get_account_lock,
    prune_idle_account_locks,
)


@pytest.mark.asyncio
async def test_get_account_lock_returns_same_lock_for_same_id():
    account_id = uuid4()
    lock_a = await get_account_lock(account_id)
    lock_b = await get_account_lock(account_id)
    assert lock_a is lock_b


@pytest.mark.asyncio
async def test_get_account_lock_returns_different_locks_for_different_ids():
    lock_a = await get_account_lock(uuid4())
    lock_b = await get_account_lock(uuid4())
    assert lock_a is not lock_b


@pytest.mark.asyncio
async def test_account_lock_serializes_concurrent_critical_sections():
    """같은 계좌의 두 코루틴이 임계 영역에 동시 진입하지 못함을 검증."""
    account_id = uuid4()
    timeline: list[str] = []

    async def cycle(name: str):
        lock = await get_account_lock(account_id)
        async with lock:
            timeline.append(f"{name}-enter")
            await asyncio.sleep(0.05)
            timeline.append(f"{name}-exit")

    await asyncio.gather(cycle("A"), cycle("B"))

    # enter/exit이 인터리브되지 않고 쌍으로 묶여있어야 함
    assert timeline[0].endswith("-enter")
    assert timeline[1].endswith("-exit")
    assert timeline[0].split("-")[0] == timeline[1].split("-")[0]
    assert timeline[2].endswith("-enter")
    assert timeline[3].endswith("-exit")
    assert timeline[2].split("-")[0] == timeline[3].split("-")[0]


@pytest.mark.asyncio
async def test_clear_account_lock_removes_idle_lock():
    account_id = uuid4()
    lock_a = await get_account_lock(account_id)
    assert await clear_account_lock(account_id) is True
    # 제거 후 다시 호출하면 새 인스턴스가 생성되어야 함
    lock_b = await get_account_lock(account_id)
    assert lock_a is not lock_b


@pytest.mark.asyncio
async def test_clear_account_lock_refuses_when_locked():
    account_id = uuid4()
    lock = await get_account_lock(account_id)
    async with lock:
        assert await clear_account_lock(account_id) is False
    # 풀린 후엔 제거 가능
    assert await clear_account_lock(account_id) is True


@pytest.mark.asyncio
async def test_clear_account_lock_returns_true_for_unknown_id():
    assert await clear_account_lock(uuid4()) is True


@pytest.mark.asyncio
async def test_prune_idle_account_locks_removes_only_idle():
    idle_id = uuid4()
    busy_id = uuid4()
    await get_account_lock(idle_id)
    busy_lock = await get_account_lock(busy_id)
    async with busy_lock:
        removed = await prune_idle_account_locks()
        assert removed >= 1
        # busy는 살아있어야 함
        assert (await get_account_lock(busy_id)) is busy_lock


@pytest.mark.asyncio
async def test_different_accounts_do_not_block_each_other():
    """서로 다른 계좌는 동시 실행 가능해야 함."""
    id_a, id_b = uuid4(), uuid4()
    started = asyncio.Event()
    other_entered = asyncio.Event()

    async def hold_a():
        lock = await get_account_lock(id_a)
        async with lock:
            started.set()
            await asyncio.wait_for(other_entered.wait(), timeout=1.0)

    async def enter_b():
        await started.wait()
        lock = await get_account_lock(id_b)
        async with lock:
            other_entered.set()

    await asyncio.gather(hold_a(), enter_b())
