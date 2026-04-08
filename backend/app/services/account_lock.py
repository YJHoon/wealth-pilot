"""계좌 단위 asyncio.Lock 관리.

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

"""

from __future__ import annotations

import asyncio
from uuid import UUID

_account_locks: dict[UUID, asyncio.Lock] = {}
_registry_lock = asyncio.Lock()


async def get_account_lock(account_id: UUID) -> asyncio.Lock:
    """계좌 ID에 대응되는 asyncio.Lock을 반환 (없으면 생성)."""
    async with _registry_lock:
        lock = _account_locks.get(account_id)
        if lock is None:
            lock = asyncio.Lock()
            _account_locks[account_id] = lock
        return lock
