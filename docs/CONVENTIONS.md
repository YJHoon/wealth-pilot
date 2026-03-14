# CONVENTIONS.md — WealthPilot 코딩 컨벤션

## 공통

- 변수명/함수명: 영어 (camelCase for TS, snake_case for Python)
- 주석: 한국어 허용, 복잡한 비즈니스 로직에 필수
- 커밋 메시지: Conventional Commits (`feat:`, `fix:`, `refactor:`, `security:`)
- Git Flow: feature → develop → main
- 에러 메시지: 한국어 (사용자용), 영어 (로그용)

## 프론트엔드 (TypeScript/Next.js)

- App Router 사용 (pages/ 아님)
- 서버 컴포넌트 기본, 클라이언트는 `"use client"` 명시
- shadcn/ui 컴포넌트 우선, 없으면 Tailwind로 직접 구현
- shadcn 추가: `npx shadcn-ui@latest add [component]`
- 상태관리: 로컬은 `useState`, 글로벌은 Zustand
  - `viewMode`: `'minimal' | 'terminal'`
  - `isMasked`: `boolean` (금액 마스킹)
  - `theme`: `'dark' | 'light'`
- API 호출: fetch 기본, 복잡하면 SWR 또는 React Query
- 컴포넌트 파일명: PascalCase (예: `AssetCard.tsx`)

## 백엔드 (Python/FastAPI)

- Pydantic v2 스키마로 request/response 검증
- SQLAlchemy 2.0 스타일 (`select()` 문법)
- 비즈니스 로직은 `services/`에, 라우터는 얇게 유지
- DB 마이그레이션은 반드시 Alembic으로 관리
- 환경변수: pydantic-settings로 관리 (`config.py`)
- 비동기 함수 우선 (`async def`)

## 금융 데이터 규칙

- 금액 표시: 원화는 천 단위 쉼표 + "원", 달러는 $+소수점 2자리
- 해외자산: 원화 + 원래 통화 병기 (예: `"$150 / 195,000원"`)
- 수익률: 소수점 2자리 + %, 양수 초록(+) / 음수 빨강(-)
- 수익률 표시: 기본 합산, 탭으로 실현/미실현 분리
- 모든 금융 데이터 화면에 "데이터 갱신 시각" 표시 필수
- 면책 고지: 분석/시그널 화면에 항상 표시
- 환율 계산: `Decimal` 타입 사용 (float 금지)
- 금액 마스킹: `isMasked=true`일 때 `"●●●●●●원"` 표시

## 새 기능 추가 순서

DB 모델 → Alembic 마이그레이션 → API 엔드포인트 → 프론트 UI