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
- **배포**: Vercel (프론트, xxx.vercel.app) + Railway (백엔드)
- **알림**: Telegram Bot API (뉴스 + 시세 + 보안)
- **모니터링**: Sentry + 텔레그램 에러 알림
- **테스트**: pytest (API) + React Testing Library (컴포넌트)
- **Git**: Git Flow (main/develop/feature 브랜치)

## 디렉토리 구조

```
wealthpilot/
├── frontend/          # Next.js 앱
│   └── src/
│       ├── app/       # App Router 페이지
│       ├── components/
│       │   ├── ui/         # shadcn/ui
│       │   ├── dashboard/  # 대시보드 (미니멀 + 터미널)
│       │   ├── assets/     # 자산 관리
│       │   ├── groups/     # 포트폴리오 그룹
│       │   ├── analysis/   # 종목 분석 (기본+기술)
│       │   ├── spending/   # 지출 분석
│       │   ├── news/       # 뉴스 큐레이터
│       │   ├── security/   # 보안 (2FA, 세션, 로그)
│       │   └── onboarding/ # 튜토리얼 위저드
│       ├── hooks/     # 커스텀 훅
│       ├── lib/       # 유틸리티 (포맷팅, 암호화)
│       ├── stores/    # Zustand (viewMode, masking, theme)
│       └── types/     # TypeScript 타입
├── backend/           # FastAPI 앱
│   └── app/
│       ├── models/    # SQLAlchemy 모델
│       ├── schemas/   # Pydantic v2 스키마
│       ├── routers/   # API 라우터
│       ├── services/  # 비즈니스 로직
│       │   ├── crypto_service.py   # AES-256 암복호화
│       │   ├── security_service.py # 2FA, 세션, 로그
│       │   └── alert_service.py    # 텔레그램 알림
│       ├── middleware/ # 인증, Rate Limit, 액세스 로깅
│       └── tasks/     # 크론잡 (시세갱신, 데이터정리)
└── docs/              # PRD.md, API.md, DEPLOYMENT.md
```

## 보안 규칙 (최우선)

이 프로젝트에서 보안은 편의성보다 항상 우선한다.

### 암호화 필수 필드
다음 필드는 반드시 AES-256으로 암호화하여 DB에 저장:
- assets: quantity, purchase_price, sold_price, realized_pnl
- asset_snapshots: total_value_krw
- transactions: amount

### 인증 규칙
- Google OAuth + TOTP 2FA 필수 (2FA 미설정 시 강제 설정 유도)
- JWT Access Token: 15분 만료
- Refresh Token: 7일 만료
- 30분 미사용 시 자동 로그아웃
- 새 기기 로그인 시 텔레그램 알림

### 모든 API에 적용할 것
- JWT 인증 미들웨어
- 사용자 소유권 검증 (본인 데이터만 접근)
- 액세스 로그 기록 (로그인, 자산 변경 등)
- Rate Limiting (100 req/min per user)

### 절대 하지 말 것
- raw SQL 쿼리 사용 금지 (SQLAlchemy ORM만)
- 환경변수를 코드에 하드코딩 금지
- API 응답에 불필요한 민감 정보 포함 금지
- 암호화 없이 금액 데이터 DB 저장 금지

## 코딩 컨벤션

### 공통
- 변수명/함수명: 영어 (camelCase for TS, snake_case for Python)
- 주석: 한국어 허용, 복잡한 비즈니스 로직에 필수
- 커밋 메시지: Conventional Commits (`feat:`, `fix:`, `refactor:`, `security:`)
- Git Flow: feature → develop → main
- 에러 메시지: 한국어 (사용자용), 영어 (로그용)

### 프론트엔드 (TypeScript/Next.js)
- App Router 사용 (pages/ 아님)
- 서버 컴포넌트 기본, 클라이언트는 "use client" 명시
- shadcn/ui 컴포넌트 우선, 없으면 Tailwind로 직접 구현
- 상태관리: 로컬은 useState, 글로벌은 Zustand
  - viewMode: 'minimal' | 'terminal'
  - isMasked: boolean (금액 마스킹)
  - theme: 'dark' | 'light'
- API 호출: fetch 기본, 복잡하면 SWR 또는 React Query
- 컴포넌트 파일명: PascalCase (예: AssetCard.tsx)

### 백엔드 (Python/FastAPI)
- Pydantic v2 스키마로 request/response 검증
- SQLAlchemy 2.0 스타일 (select() 문법)
- 비즈니스 로직은 services/에, 라우터는 얇게 유지
- DB 마이그레이션은 반드시 Alembic으로 관리
- 환경변수: pydantic-settings로 관리 (config.py)
- 비동기 함수 우선 (async def)

### 금융 데이터 규칙
- 금액 표시: 원화는 천 단위 쉼표 + "원", 달러는 $+소수점 2자리
- 해외자산: 원화 + 원래 통화 병기 (예: "$150 / 195,000원")
- 수익률: 소수점 2자리 + %, 양수 초록(+) / 음수 빨강(-)
- 수익률 표시: 기본 합산, 탭으로 실현/미실현 분리
- 모든 금융 데이터 화면에 "데이터 갱신 시각" 표시 필수
- 면책 고지: 분석/시그널 화면에 항상 표시
- 환율 계산: Decimal 타입 사용 (부동소수점 오류 방지)
- 금액 마스킹: isMasked=true일 때 "●●●●●●원" 표시

### API 실패 처리
- 시세 API 실패 시: 해당 부분만 빈칸 (또는 마지막 캐시 + "오래됨" 라벨)
- 나머지 UI는 정상 동작 유지
- 에러 토스트로 사용자에게 상황 안내
- Sentry에 에러 기록 + 텔레그램 알림

## 자주 사용하는 명령어

```bash
# 프론트엔드
cd frontend && npm run dev          # 개발 서버
cd frontend && npm run build        # 프로덕션 빌드
cd frontend && npm run lint         # ESLint
cd frontend && npx tsc --noEmit     # 타입 체크
cd frontend && npm test             # 컴포넌트 테스트

# 백엔드
cd backend && uvicorn app.main:app --reload  # 개발 서버
cd backend && alembic upgrade head            # DB 마이그레이션 실행
cd backend && alembic revision --autogenerate -m "설명"  # 마이그레이션 생성
cd backend && pytest                          # API 테스트
cd backend && pytest --cov=app                # 커버리지 포함

# Git Flow
git checkout develop
git checkout -b feature/기능명
# ... 작업 ...
git checkout develop && git merge feature/기능명
git checkout main && git merge develop  # 릴리즈 시

# 전체
docker compose up -d                # 로컬 PostgreSQL (개발용)
```

## 작업 시 주의사항

1. **새 기능 추가 시**: DB 모델 → Alembic 마이그레이션 → API 엔드포인트 → 프론트 UI 순서
2. **금액 필드 추가 시**: 반드시 crypto_service.py의 암복호화 적용
3. **API 변경 시**: Pydantic 스키마 먼저 정의, 프론트 types/ 동시 업데이트
4. **환경변수 추가 시**: backend/.env.example, frontend/.env.example 모두 업데이트
5. **shadcn/ui 컴포넌트 추가**: `npx shadcn-ui@latest add [component]`
6. **보안 관련 변경 시**: security_service.py 업데이트 + 테스트 필수
7. **테스트**: API 엔드포인트 추가 시 pytest 테스트 함께 작성, 컴포넌트 추가 시 RTL 테스트 작성

## 현재 Phase

**Phase 1: 자산 대시보드 MVP** — 자산 CRUD + 매도 아카이브 + 포트폴리오 그룹 + 대시보드(미니멀/터미널) + 2FA 인증 + 보안 + 배포

## 참고 문서

- PRD: `docs/PRD.md`
- API 명세: `docs/API.md`
- 배포 가이드: `docs/DEPLOYMENT.md`
