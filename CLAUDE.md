# CLAUDE.md — WealthPilot 프로젝트 지침

> Claude Code가 이 프로젝트에서 작업할 때 따라야 할 규칙과 컨텍스트

---

## 프로젝트 개요

WealthPilot은 개인 자산 관리 플랫폼이다. Next.js 프론트엔드 + FastAPI 백엔드 모노레포 구조.
한국어 UI, 한국 사용자 대상 금융 서비스. **보안 최우선 프로젝트.**

## 기술 스택

- **프론트엔드**: Next.js 14+ (App Router), TypeScript, shadcn/ui, Tailwind CSS, Recharts, Zustand
- **백엔드**: FastAPI, Python 3.11+, SQLAlchemy 2.0, Alembic, Pydantic v2
- **DB**: PostgreSQL (Supabase 또는 Neon) — 금액 필드 AES-256 암호화 필수
- **인증**: NextAuth.js v5 (Google OAuth) + TOTP 2FA 필수
- **배포**: Vercel (프론트) + Railway (백엔드)
- **알림**: Telegram Bot API / **모니터링**: Sentry + 텔레그램
- **테스트**: pytest (API) + React Testing Library (컴포넌트)
- **Git**: Git Flow (main/develop/feature)

## 디렉토리 구조

```text
wealthpilot/
├── frontend/src/
│   ├── app/            # App Router
│   ├── components/     # ui/ dashboard/ assets/ groups/ analysis/ spending/ news/ security/ onboarding/
│   ├── hooks/
│   ├── lib/            # 유틸리티, 암호화
│   ├── stores/         # Zustand (viewMode, masking, theme)
│   └── types/
├── backend/app/
│   ├── models/         # SQLAlchemy
│   ├── schemas/        # Pydantic v2
│   ├── routers/
│   ├── services/       # crypto_service.py, security_service.py, alert_service.py
│   ├── middleware/
│   └── tasks/          # 크론잡
└── docs/               # PRD.md, API.md, SECURITY.md, CONVENTIONS.md, DEPLOYMENT.md
```

## 보안 핵심 규칙 (최우선)

> 상세 규칙: `docs/SECURITY.md`

- **암호화 필수 필드** (AES-256): `assets.quantity`, `purchase_price`, `sold_price`, `realized_pnl` / `asset_snapshots.total_value_krw` / `transactions.amount`
- JWT: Access 15분, Refresh 7일 / 30분 미사용 자동 로그아웃
- 모든 API: JWT 인증 + 소유권 검증 + 액세스 로그 + Rate Limit (100 req/min)
- raw SQL 금지 (ORM만) / 환경변수 하드코딩 금지 / 금액 미암호화 DB 저장 금지

## 코딩 컨벤션 요약

> 상세 규칙: `docs/CONVENTIONS.md`

- 커밋: Conventional Commits (`feat:` `fix:` `refactor:` `security:`)
- TS: camelCase / Python: snake_case
- 에러 메시지: 사용자용 한국어, 로그용 영어
- 금융 금액: Decimal 타입 (float 금지) / 환율: 원화+원래통화 병기
- 금액 마스킹: `isMasked=true` → `"●●●●●●원"`

## 자주 사용하는 명령어

```bash
# 프론트엔드
cd frontend && npm run dev
cd frontend && npm run lint && npx tsc --noEmit
cd frontend && npm test

# 백엔드
cd backend && uvicorn app.main:app --reload
cd backend && pytest -x -q --tb=short
cd backend && pytest --cov=app
cd backend && alembic upgrade head
cd backend && alembic revision --autogenerate -m "설명"

# Git Flow
git checkout -b feature/기능명 develop
git checkout develop && git merge feature/기능명
```

## 작업 시 체크리스트

1. 금액 필드 추가 → `crypto_service.py` 암복호화 적용
2. API 변경 → Pydantic 스키마 + 프론트 `types/` 동시 업데이트
3. 환경변수 추가 → `backend/.env.example` + `frontend/.env.example` 업데이트
4. 새 API 엔드포인트 → pytest 테스트 함께 작성
5. 새 컴포넌트 → RTL 테스트 함께 작성
6. 보안 변경 → `security_service.py` 업데이트 + 테스트 필수
7. DB 모델 변경 → Alembic 마이그레이션 생성

## 참고 문서

- PRD: `docs/PRD.md`
- API 명세: `docs/API.md`
- 보안 상세: `docs/SECURITY.md`
- 컨벤션 상세: `docs/CONVENTIONS.md`
- 배포 가이드: `docs/DEPLOYMENT.md`

## 웹소켓 사용 주의사항 (외부 API 공지 기준)

실시간 웹소켓 연결 시 아래 비정상 패턴이 발생하지 않도록 구현할 것.

### 정상 플로우
연결 → 종목 구독 → 데이터 수신 → 불필요 종목 구독 해제 → 연결 종료

### 금지 패턴
- 연결 후 즉시 종료를 반복하는 루프 구현 금지
- 데이터 수신 확인 없이 구독/해제를 무한 반복하는 로직 금지

### 구현 시 체크 포인트
- 재연결 로직에는 반드시 backoff(지수 백오프 권장) 적용
- 구독 후 수신 확인(ACK or 데이터 도착) 검증 후 다음 동작 진행
- 연결 상태 관리는 단일 인스턴스로 유지 (중복 연결 방지)

## Agent Workflow

복잡한 작업은 `.claude/orchestrator.md`의 워크플로우를 따른다.
"오케스트레이터로 실행" 또는 "agent workflow로 실행" 명시 시에만 동작한다.