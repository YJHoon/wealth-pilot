"""계좌 단위 asyncio.Lock 관리 (refcount 기반).

같은 계좌에서 여러 전략이 동시에 매매 사이클을 돌릴 때
잔고조회→판단→발주 구간이 인터리브되어 잔고를 초과 매수하는 것을 막는다.

프로세스 내에서만 유효하다 (멀티 워커/멀티 인스턴스 환경에서는 분산 락 필요).

TODO(Phase 2 / 스케일아웃 전): Redis 기반 분산 락으로 교체할 것.
권장 라이브러리:
  - aioredlock (Redlock 알고리즘, 다중 Redis 노드 지원)
  - redis-py 의 redis.asyncio.lock.Lock (단일 Redis로 충분한 경우)
운영 체크리스트:
  1) Redis 인스턴스 준비 + 연결 풀
  2) 락 키 네임스페이스: f"wp:account_lock:{account_id}"
  3) TTL = 매매 사이클 최대 시간 + 여유분 (예: 60s)
  4) 락 획득 실패 시 사이클 스킵 + 알림

## 사용법

권장 — 컨텍스트 매니저(refcount 자동 관리):

    async with acquire_account_lock(account_id):
        ...  # 임계 구간

저수준 API (`get_account_lock`)는 테스트/특수 케이스에서만 사용하고,
직접 쓸 경우 반드시 try/finally로 `release_account_lock(account_id)`를
호출해 refcount를 감소시켜야 한다. 그렇지 않으면 prune이 락을 회수하지
못해 누수가 발생한다.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncIterator
from uuid import UUID


@dataclass
class _LockEntry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    refcount: int = 0  # get_account_lock 발급 후 release 전까지 유지


_account_locks: dict[UUID, _LockEntry] = {}
_registry_lock = asyncio.Lock()


async def get_account_lock(account_id: UUID) -> asyncio.Lock:
    """계좌 락 인스턴스를 반환하고 refcount를 1 증가시킨다.

    호출 측은 사용 종료 시 반드시 `release_account_lock(account_id)`를
    호출해야 한다. 누락 시 락 객체가 영구적으로 회수되지 않는다.

    가능한 한 `acquire_account_lock(...)` 컨텍스트 매니저를 사용할 것.
    """
    async with _registry_lock:
        entry = _account_locks.get(account_id)
        if entry is None:
            entry = _LockEntry()
            _account_locks[account_id] = entry
        entry.refcount += 1
        return entry.lock


async def release_account_lock(account_id: UUID) -> None:
    """refcount를 1 감소. 0이 되어도 즉시 제거하지 않고 prune에 위임."""
    async with _registry_lock:
        entry = _account_locks.get(account_id)
        if entry is None:
            return
        if entry.refcount > 0:
            entry.refcount -= 1


@asynccontextmanager
async def acquire_account_lock(account_id: UUID) -> AsyncIterator[asyncio.Lock]:
    """refcount 안전한 컨텍스트 매니저.

    - 진입 전: registry에 entry 등록 + refcount 증가 + lock.acquire
    - 진입 중: prune이 이 entry를 절대 회수하지 못함 (refcount > 0)
    - 종료 후: lock.release + refcount 감소
    """
    lock = await get_account_lock(account_id)
    try:
        await lock.acquire()
        try:
            yield lock
        finally:
            lock.release()
    finally:
        await release_account_lock(account_id)


async def clear_account_lock(account_id: UUID) -> bool:
    """레지스트리에서 계좌 락을 제거.

    계좌 삭제/비활성화 시 호출. refcount > 0 또는 lock.locked() 인 경우
    제거하지 않고 False를 반환한다.

    Returns:
        True: 제거 성공 또는 애초에 없었음
        False: 사용 중이라 제거하지 못함
    """
    async with _registry_lock:
        entry = _account_locks.get(account_id)
        if entry is None:
            return True
        if entry.refcount > 0 or entry.lock.locked():
            return False
        _account_locks.pop(account_id, None)
        return True


async def prune_idle_account_locks() -> int:
    """refcount=0 이고 점유되지 않은 모든 항목 제거.

    refcount > 0 인 entry는 사용 중인 호출자가 있을 수 있으므로 반드시
    유지한다. 이로써 TOCTOU 경합(획득 직전에 prune이 끼어들어 다른 락을
    재생성하는 문제)이 차단된다.

    Returns: 제거된 개수
    """
    async with _registry_lock:
        idle_ids = [
            aid
            for aid, entry in _account_locks.items()
            if entry.refcount == 0 and not entry.lock.locked()
        ]
        for aid in idle_ids:
            _account_locks.pop(aid, None)
        return len(idle_ids)


def _registry_size() -> int:
    """테스트/디버깅용 — 현재 등록된 entry 수."""
    return len(_account_locks)
