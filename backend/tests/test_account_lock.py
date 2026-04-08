"""account_lock 모듈 테스트 — 계좌 단위 직렬화 검증."""

import asyncio
from uuid import uuid4

import pytest

from app.services.account_lock import get_account_lock


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
