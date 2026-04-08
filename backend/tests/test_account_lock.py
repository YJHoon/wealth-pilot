"""account_lock 모듈 테스트 — 계좌 단위 직렬화 + refcount 검증."""

import asyncio
from uuid import uuid4

import pytest

from app.services.account_lock import (
    _registry_size,
    acquire_account_lock,
    clear_account_lock,
    get_account_lock,
    prune_idle_account_locks,
    release_account_lock,
)


@pytest.mark.asyncio
async def test_get_account_lock_returns_same_lock_for_same_id():
    account_id = uuid4()
    lock_a = await get_account_lock(account_id)
    lock_b = await get_account_lock(account_id)
    assert lock_a is lock_b
    await release_account_lock(account_id)
    await release_account_lock(account_id)


@pytest.mark.asyncio
async def test_get_account_lock_returns_different_locks_for_different_ids():
    a, b = uuid4(), uuid4()
    lock_a = await get_account_lock(a)
    lock_b = await get_account_lock(b)
    assert lock_a is not lock_b
    await release_account_lock(a)
    await release_account_lock(b)


@pytest.mark.asyncio
async def test_acquire_serializes_concurrent_critical_sections():
    account_id = uuid4()
    timeline: list[str] = []

    async def cycle(name: str):
        async with acquire_account_lock(account_id):
            timeline.append(f"{name}-enter")
            await asyncio.sleep(0.05)
            timeline.append(f"{name}-exit")

    await asyncio.gather(cycle("A"), cycle("B"))

    assert timeline[0].endswith("-enter")
    assert timeline[1].endswith("-exit")
    assert timeline[0].split("-")[0] == timeline[1].split("-")[0]
    assert timeline[2].endswith("-enter")
    assert timeline[3].endswith("-exit")
    assert timeline[2].split("-")[0] == timeline[3].split("-")[0]


@pytest.mark.asyncio
async def test_acquire_releases_refcount_on_exit():
    account_id = uuid4()
    async with acquire_account_lock(account_id):
        pass
    # refcount=0이면 prune이 회수 가능
    removed = await prune_idle_account_locks()
    assert removed >= 1


@pytest.mark.asyncio
async def test_clear_account_lock_removes_idle_lock():
    account_id = uuid4()
    lock_a = await get_account_lock(account_id)
    await release_account_lock(account_id)
    assert await clear_account_lock(account_id) is True
    lock_b = await get_account_lock(account_id)
    assert lock_a is not lock_b
    await release_account_lock(account_id)


@pytest.mark.asyncio
async def test_clear_account_lock_refuses_when_in_use():
    account_id = uuid4()
    async with acquire_account_lock(account_id):
        # 사용 중(refcount>0 + locked)이므로 제거 거부
        assert await clear_account_lock(account_id) is False
    # 컨텍스트 종료 후엔 제거 가능
    assert await clear_account_lock(account_id) is True


@pytest.mark.asyncio
async def test_clear_account_lock_refuses_when_refcount_only():
    account_id = uuid4()
    await get_account_lock(account_id)  # refcount=1, not locked
    assert await clear_account_lock(account_id) is False
    await release_account_lock(account_id)
    assert await clear_account_lock(account_id) is True


@pytest.mark.asyncio
async def test_clear_account_lock_returns_true_for_unknown_id():
    assert await clear_account_lock(uuid4()) is True


@pytest.mark.asyncio
async def test_prune_skips_entries_with_outstanding_refcount():
    """TOCTOU 방어: refcount > 0 인 entry는 prune 대상에서 제외."""
    holder_id = uuid4()
    idle_id = uuid4()
    # holder는 refcount만 보유 (락 미획득)
    holder_lock = await get_account_lock(holder_id)
    # idle은 발급 후 즉시 release
    await get_account_lock(idle_id)
    await release_account_lock(idle_id)

    await prune_idle_account_locks()

    # holder는 살아있어야 — 같은 인스턴스 반환
    assert (await get_account_lock(holder_id)) is holder_lock
    await release_account_lock(holder_id)
    await release_account_lock(holder_id)


@pytest.mark.asyncio
async def test_prune_removes_only_zero_refcount_and_unlocked():
    a, b = uuid4(), uuid4()
    await get_account_lock(a)
    await release_account_lock(a)  # refcount=0, unlocked → 회수 대상
    busy_lock = await get_account_lock(b)  # refcount=1 → 보존
    try:
        before = _registry_size()
        removed = await prune_idle_account_locks()
        assert removed >= 1
        assert _registry_size() == before - removed
        # b 는 그대로
        assert (await get_account_lock(b)) is busy_lock
        await release_account_lock(b)
    finally:
        await release_account_lock(b)


@pytest.mark.asyncio
async def test_different_accounts_do_not_block_each_other():
    id_a, id_b = uuid4(), uuid4()
    started = asyncio.Event()
    other_entered = asyncio.Event()

    async def hold_a():
        async with acquire_account_lock(id_a):
            started.set()
            await asyncio.wait_for(other_entered.wait(), timeout=1.0)

    async def enter_b():
        await started.wait()
        async with acquire_account_lock(id_b):
            other_entered.set()

    await asyncio.gather(hold_a(), enter_b())
