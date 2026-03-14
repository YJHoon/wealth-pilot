# WealthPilot — Product Requirements Document (PRD)

> 통합 개인 자산 관리 플랫폼
> 작성일: 2026-03-09 | 버전: 2.1 (구현 현황 반영)

---

## 1. 프로젝트 개요

### 1.1 비전
흩어진 개인 자산 정보를 한 곳에서 관리하고, 종목 밸류에이션 분석·지출 패턴·AI 뉴스 큐레이션까지 제공하는 올인원 자산 관리 플랫폼.

### 1.2 목표
- Claude Code를 활용한 바이브코딩 학습 프로젝트
- MVP에서 시작하여 단계적으로 고도화하는 확장 가능한 아키텍처
- 개인 사용 → 멀티유저 서비스로 확장 가능한 구조
- 월 추가 비용 0~3만원 이내 운영
- 보안 최우선 — 사용자가 불편하더라도 자산 정보 보호가 우선

### 1.3 핵심 사용자
- 1차: 본인 (개발자, 코인·국내주식·해외주식·현금 보유)
- 2차: 자산 관리에 관심 있는 일반 사용자 (멀티유저 확장 시)
- 현재 자산 관리 상태: 머릿속으로만 대충 파악 중 → 이 앱으로 체계화

### 1.4 사용 패턴
- 수시: 생각날 때마다 자산 현황 체크
- 투자 전: 종목 분석·시뮬레이션 돌릴 때
- 매일: AI 뉴스 큐레이터 확인 (텔레그램 알림)

---

## 2. 기술 스택

| 영역 | 기술 | 선택 이유 |
|------|------|-----------|
| 프론트엔드 | Next.js 14+ (App Router) | SSR/SSG, Vercel 배포 궁합, API Routes 활용 |
| UI 라이브러리 | shadcn/ui + Tailwind CSS | 사용자 선호(Tailwind), 커스터마이징 용이, 다크모드, 트렌디 |
| 차트 | Recharts (기본) + TradingView Lightweight Charts (고급) | 대시보드↔트레이딩 모드 전환 |
| 상태관리 | Zustand | 경량, 간단한 API, 모드 전환 등 글로벌 상태 |
| 백엔드 | FastAPI (Python 3.11+) | 금융 라이브러리(yfinance, pandas) 생태계, 비동기 지원 |
| DB | PostgreSQL (Supabase 또는 Neon 무료) | 관계형 데이터, JSONB 지원, RLS 보안 |
| ORM | SQLAlchemy 2.0 + Alembic | 마이그레이션 관리, 타입 안전성 |
| 인증 | NextAuth.js v5 + TOTP 2FA | Google 소셜 로그인 + OTP 2차 인증 필수 |
| 배포 (프론트) | Vercel (xxx.vercel.app) | 무료, 커스텀 도메인 불필요 |
| 배포 (백엔드) | Railway 또는 Fly.io | FastAPI 호스팅, 무료~$5/월 |
| 모바일 | PWA (next-pwa) | 홈화면 설치, 오프라인 지원 |
| 알림 | Telegram Bot API | 무료, 실시간 푸시, 보안 알림 + 뉴스 + 시그널 |
| 에러 모니터링 | Sentry (무료) + 텔레그램 알림 | 금융 데이터 API 실패 감지 중요 |
| 테스트 | pytest (API) + React Testing Library (컴포넌트) | API + 프론트 컴포넌트 테스트 |
| 저장소 구조 | 모노레포 (추후 분리 가능) | Claude Code 컨텍스트 공유 용이 |
| Git 전략 | Git Flow (main/develop/feature) | 체계적 브랜치 관리 |

### 2.1 언어
- UI: 한국어 전용
- 코드/변수명: 영어
- 주석/문서: 한국어 허용

---

## 3. 핵심 기능 (Phase별)

### Phase 1: 자산 대시보드 MVP (1주일)
> 목표: 내 모든 자산을 한 화면에서 보기

**핵심 기능:**
- 자산 등록/수정/삭제
  - Open API로 자동 가져오기 우선, 불가 시 수동 입력
  - 현금/예적금: 금액, 은행명, 이율
  - 국내주식: 종목명, 종목코드, 수량, 매입가
  - 해외주식/ETF: 종목명, 티커, 수량, 매입가, 통화
  - 코인: 종목명, 심볼, 수량, 매입가
  - 부동산/전세보증금: 평가액 (확장용, MVP에서 선택적)
- 포트폴리오 그룹핑
  - 커스텀 그룹 생성 (예: '장기투자', '단기트레이딩', '배당주')
  - 자산을 그룹에 할당, 그룹별 수익률/비중 표시
- 총 자산 요약 대시보드
  - 순자산 총액 (원화 환산)
  - 자산 유형별 비중 (파이차트)
  - 자산 변동 추이 (라인차트, 일/주/월)
- 해외자산 금액 표시: **원화 + 원래 통화 병기** (예: $150 / 195,000원)
- 환율 자동 반영 (USD/KRW 등)
- UI 모드 전환: 미니멀 모드 ↔ 트레이딩 터미널 모드
- 자산 금액 마스킹 토글 (눈 아이콘으로 금액 숨기기/보이기)

**매도 처리: 아카이브 방식**
- 매도 시 자산이 '매도 완료' 상태로 아카이브
- 실현 손익 자동 계산 및 기록
- 매도 대금은 현금 자산에 자동 반영
- 거래 이력에서 과거 매도 기록 언제든 조회 가능

**수익률 표시:**
- 기본: 실현 손익 + 미실현 손익 합산 표시
- 탭 전환: 실현(매도 완료분) / 미실현(보유 중) 분리 조회
- 양수 초록(+), 음수 빨강(-), 소수점 2자리 + %

**온보딩 (첫 가입 사용자):**
- 튜토리얼 위저드로 자산 유형별 안내하며 등록
- 단계: 환영 → 자산 유형 선택 → 유형별 입력 가이드 → 대시보드 도착
- 스킵 가능, 나중에 다시 볼 수 있는 도움말

**데이터 소스 (무료):**
- 환율: ExchangeRate-API (무료 1,500회/월) 또는 한국은행 Open API
- 국내 주식: KRX 시세 (한국거래소 Open API)
- 해외 주식: Yahoo Finance (yfinance 라이브러리)
- 코인: CoinGecko API (무료 30회/분)

**시세 데이터 모드 (3단계, 사용자 선택 가능):**
1. 배치 모드: 하루 1회 업데이트, 크론잡
2. 지연 모드: 5~15분 주기 자동 갱신
3. 실시간 모드: 웹소켓 연결 (유료 API 필요할 수 있음 — 면책 고지 포함)

**API 실패 시 UI 동작:**
- 시세 부분만 빈칸(또는 마지막 성공 데이터 + "오래됨" 표시)
- 나머지 UI는 정상 동작
- 에러 토스트로 사용자에게 상황 안내

### Phase 2: 지출 패턴 분석기 (2주차)
> 목표: 소비 습관을 데이터로 파악

**핵심 기능:**
- 지출 데이터 직접 수동 입력
  - 날짜, 금액, 설명, 카테고리 입력 폼
  - 빠른 입력 UI (최소 필드로 간편 등록)
- 자동 카테고리 분류
  - 규칙 기반 분류 (키워드 매칭)
  - 사용자 커스텀 분류 규칙 추가
- 지출 분석 대시보드
  - 카테고리별 지출 비율 (도넛차트)
  - 월별 지출 트렌드 (바차트)
  - 전월 대비 증감 분석
  - "라떼 팩터" — 소액 반복 지출 인사이트
- 절약 시뮬레이션: "매일 커피를 줄이면 N년 후 X원 절약"

### Phase 3: 투자 종목 분석기 (3~4주차)
> 목표: 종목의 가치를 평가하고 매매 판단 돕기

**기본적 분석 (Fundamental):**
- PER, PBR, ROE, EPS 등 핵심 지표
- 동종 업계 비교 (Peer Comparison)
- 적정가 추정 (DCF 간이 모델)
- 과대평가/과소평가 판정 (신호등 시스템: 🟢저평가 🟡적정 🔴고평가)

**기술적 분석 (Technical):**
- RSI, MACD, 볼린저밴드 차트
- 이동평균선 (5/20/60/120일)
- 지지선/저항선 자동 탐지

**매매 시그널 (참고용, 면책 고지 필수):**
- "현재 가격 대비 적정가 괴리율"
- 매수/매도/관망 시그널
- 리스크 레벨 표시 (상/중/하)
- 목표 매수가/매도가 설정 → 도달 시 텔레그램 알림

**포트폴리오 시뮬레이션:**
- 가상 매매: 종목 추가 시 포트폴리오 변화 시뮬레이션
- DCA 시뮬레이터: "매월 X원씩 이 종목에 넣으면?"
- 리밸런싱 제안

**면책 고지 (필수 구현):**
- 모든 분석 화면에 "투자 참고용이며, 투자 손실에 대한 책임은 사용자에게 있습니다" 상시 표시
- "과거 성과가 미래를 보장하지 않습니다" 명시
- 데이터 소스 및 갱신 시각 명시
- 데이터 신뢰도 등급 표시 (실시간 / 지연 / 추정치)
- 집중 투자 경고: 단일 종목 비중 30% 이상 시 분산 투자 안내
- 첫 사용 시 면책 동의 팝업 필수

### Phase 4: AI 뉴스 큐레이터 (5~6주차)
> 목표: 관심 분야 뉴스를 AI가 요약해서 전달

**뉴스 수집 (RSS 크롤러):**
- 국내 주식: 한경, 매경, 연합인포맥스
- 해외 주식/ETF: Reuters, Bloomberg (무료 피드)
- 거시경제 (금리/환율/물가): 한국은행, FRED
- 테크/AI: TechCrunch, The Verge, GeekNews

**AI 요약 & 분류:**
- Claude API 또는 로컬 LLM으로 뉴스 요약
- 관심 키워드 매칭 & 중요도 점수
- 중복 뉴스 제거 (유사도 기반)

**뉴스 피드 UI:**
- 카테고리별 탭 뷰
- 중요도순/시간순 정렬
- 원문 링크 연결

**텔레그램 알림 (통합):**
- 매일 아침 뉴스 요약 브리핑
- 긴급 뉴스 실시간 알림
- 보유 종목 급등/급락 알림 (기본값 제공 + 사용자 커스텀 가능)
- 목표 매수/매도가 도달 알림
- 월간 자산 보고서 자동 생성 및 발송
- 비정상 로그인 감지 보안 알림
- 사용자별 관심 키워드 및 알림 설정

### Phase 5: 배포 & 고도화 (7주차~)
> 목표: 프로덕션 레벨로 끌어올리기

- CI/CD 파이프라인 (GitHub Actions) — Git Flow 기반
- Sentry 무료 플랜 + 텔레그램 에러 알림 연동
- 성능 최적화 (Lighthouse 90+ 목표)
- E2E 테스트 (Playwright)
- PWA 완성 (오프라인 지원, 푸시 알림)
- Rails로 일부 모듈 재구현하여 FastAPI와 비교 (학습 목적)
- 데이터 보관 정책 구현 (1년 보관 후 자동 삭제)

---

## 4. Phase 1 구현 현황

### ✅ 완료

#### Task 1-1. 모노레포 세팅
- Next.js 14 App Router + TypeScript + shadcn/ui v4 + Tailwind CSS 3
- FastAPI + SQLAlchemy 2.0 + Alembic + Pydantic v2
- Docker Compose로 로컬 PostgreSQL
- Zustand 스토어 (viewMode, isMasked, theme — localStorage persist)
- PWA 설정 (`@ducanh2912/next-pwa`)

#### Task 1-2. DB 모델 & 암호화 서비스
- **7개 모델 구현**: User, Session, AccessLog, PortfolioGroup, Asset, AssetSnapshot, ExchangeRate
- **AES-256-GCM 암호화 서비스** (`crypto_service.py`): `encrypt_decimal()`, `decrypt_decimal()` 등
- Alembic 마이그레이션 4건 적용

#### Task 1-3. 인증 + 2FA
- Google OAuth 로그인 (NextAuth.js v5 + 백엔드 ID Token 검증)
- TOTP 2FA 설정/검증 (pyotp + QR 코드 생성)
- JWT Access Token 15분 + Refresh Token 7일 (CAS 토큰 로테이션)
- 로그인 실패 5회 시 15분 계정 잠금
- 세션 관리 (목록 조회, 원격 종료, 로그아웃)
- 30분 미사용 자동 로그아웃 (프론트엔드 IdleTimeoutProvider)
- 프론트엔드 페이지: 로그인, 2FA 설정, 2FA 검증

#### Task 2-1. 보안 미들웨어
- Rate Limiting (SlowAPI: 전체 100 req/min, 로그인 10 req/min)
- 보안 헤더 (CSP, X-Frame-Options, X-Content-Type-Options 등)
- CORS 설정 (환경변수 기반 화이트리스트)
- 액세스 로그 기록 (LOGIN, LOGIN_CHALLENGE, LOGIN_FAILURE, LOGOUT, SESSION_REVOKE)
- 비정상 접근 탐지 (새 기기, 빠른 반복 로그인)
- 텔레그램 보안 알림 프레임워크 (`alert_service.py`)
- Sentry 연동

### ⬜ 미착수

#### Task 2-2. 자산 관리 CRUD API
- `GET/POST/PUT/DELETE /api/assets`
- `POST /api/assets/{id}/sell` (매도 처리)
- `GET/POST/PUT/DELETE /api/groups` (포트폴리오 그룹)
- Pydantic 요청/응답 스키마
- 금액 필드 암복호화 처리
- 소유권 검증 + 액세스 로그

#### Task 2-3 ~ 3-2. 시세 연동
- 시세 조회 서비스 (`price_service.py`) — 3모드 (배치/지연/실시간)
- 국내주식(yfinance), 해외주식(yfinance), 코인(CoinGecko), 환율
- 시세 API 엔드포인트
- 프론트엔드 시세 갱신 UI

#### Task 4-1 ~ 4-3. 대시보드
- `GET /api/dashboard/summary` (자산 요약)
- `GET /api/dashboard/history` (변동 추이)
- 미니멀 모드 대시보드 UI (Recharts 차트)
- 터미널 모드 대시보드 UI
- 모드 전환 토글

#### Task 5-1. 온보딩 위저드
- 환영 → 면책 동의 → 2FA 설정 → 자산 등록 가이드 → 대시보드

#### Task 5-2. 모바일 반응형 & PWA
- 반응형 레이아웃 (사이드바 햄버거, 카드 스택)
- PWA 아이콘, 오프라인 폴백

#### Task 6-*. 배포
- Vercel 배포 (프론트엔드)
- Railway 배포 (백엔드)
- Supabase/Neon DB 연결
- 시드 데이터 스크립트

#### Task 7-*. 테스트 & 마무리
- pytest API 테스트 (자산 CRUD, 대시보드, 시세)
- React Testing Library 컴포넌트 테스트
- E2E 통합 테스트

---

## 5. UI/UX 설계

### 5.1 디자인 원칙
- **듀얼 모드**: 미니멀 대시보드 ↔ 트레이딩 터미널
  - 미니멀: 깔끔한 카드 레이아웃, 핵심 숫자만 표시 (Linear/Vercel 스타일)
  - 터미널: 정보 밀도 높은 멀티패널, 실시간 차트 (TradingView 스타일)
  - 사용자가 토글로 즉시 전환 가능
  - 모바일에서는 미니멀 모드 기본 (터미널은 데스크톱 전용)
- **다크모드 기본**: 금융 앱 특성상 다크 테마 우선, 라이트모드 토글 가능
- **트렌디한 디자인**: 모던한 컬러 팔레트, 부드러운 그라데이션 액센트
- **한국어 UI**: 모든 라벨, 메시지, 에러 한국어
- **모바일 최적화**: PWA + 반응형, 터치 친화적 차트
- **금액 마스킹**: 눈 아이콘 토글로 전체 금액 숨기기/보이기

### 5.2 화면 구성

```
┌─────────────────────────────────────────────────────┐
│  WealthPilot  [미니멀|터미널] [👁마스킹] [🔔알림] [⚙설정] │
├──────────┬──────────────────────────────────────────┤
│          │                                          │
│ 사이드바   │        메인 콘텐츠                       │
│          │                                          │
│ 📊 대시보드│  [자산 요약 카드]  [실현+미실현 손익 탭]    │
│ 💰 자산    │  [자산 비중 차트] [변동 추이]              │
│ 📁 그룹    │  [포트폴리오 그룹별 뷰]                   │
│ 📉 분석    │  [종목 분석 패널 — 기본+기술]             │
│ 💳 지출    │  [지출 분석 대시보드]                     │
│ 📰 뉴스    │  [AI 뉴스 피드]                          │
│ 📜 이력    │  [매도 이력 / 거래 기록]                  │
│ 🔒 보안    │  [2FA 설정 / 세션 관리 / 액세스 로그]     │
│ ⚙️ 설정   │  [알림 설정 / 시세 모드 / 프로필]         │
│          │                                          │
└──────────┴──────────────────────────────────────────┘
```

### 5.3 핵심 사용자 플로우
1. **첫 진입**: Google 로그인 → 2FA(OTP) 설정 → 튜토리얼 위저드 → 자산 등록 → 대시보드
2. **일상 사용**: 대시보드에서 순자산 총액 + 자산 비중 한눈에 확인
3. **자산 등록**: "+ 자산 추가" → 유형 선택 → Open API 자동 or 수동 입력 → 그룹 할당
4. **종목 분석**: 검색 → 밸류에이션(기본) → 기술적 분석 차트 → 매매 시그널 확인
5. **지출 분석**: 수동 입력 → 자동 분류 → 인사이트 대시보드
6. **뉴스 확인**: 텔레그램 알림 수신 or 앱 내 뉴스 피드
7. **매도 처리**: 매도 버튼 → 매도 수량/가격 입력 → 실현 손익 기록 → 현금 반영

---

## 6. 데이터 모델

### 6.1 핵심 테이블 (Phase 1)

```
users
├── id (UUID, PK)
├── email
├── name
├── totp_secret (2FA 시크릿, 암호화 저장)
├── totp_enabled (boolean)
├── pending_totp_secret (2FA 재설정용, 암호화 저장)
├── failed_login_count (int, 기본 0)
├── locked_until (datetime, nullable)
├── onboarding_completed (boolean)
├── created_at
└── updated_at

sessions (기기별 세션 관리)
├── id (UUID, PK)
├── user_id (FK → users)
├── device_info (브라우저, OS 등)
├── ip_address
├── refresh_token_hash (토큰 재사용 방지)
├── last_active_at
├── expires_at
└── created_at

access_logs (액세스 로그)
├── id (UUID, PK)
├── user_id (FK → users)
├── action (login, logout, view_assets, etc.)
├── ip_address
├── device_info
├── is_suspicious (boolean)
├── created_at
└── expires_at (1년 후 자동 삭제용)

portfolio_groups (포트폴리오 그룹)
├── id (UUID, PK)
├── user_id (FK → users)
├── name (예: '장기투자', '단기트레이딩')
├── description
├── sort_order
└── created_at

assets
├── id (UUID, PK)
├── user_id (FK → users)
├── group_id (FK → portfolio_groups, nullable)
├── type (enum: cash, domestic_stock, foreign_stock, crypto, real_estate)
├── status (enum: active, sold, delisted)
├── name (자산명)
├── ticker (종목코드, nullable)
├── quantity (수량, encrypted)
├── purchase_price (매입가, encrypted)
├── current_price (현재가)
├── currency (KRW, USD, etc.)
├── metadata (JSONB - 유형별 추가 정보)
├── sold_at (매도 일시, nullable)
├── sold_price (매도 가격, nullable, encrypted)
├── realized_pnl (실현 손익, nullable, encrypted)
├── created_at
└── updated_at

asset_snapshots (자산 변동 추적)
├── id (UUID, PK)
├── user_id (FK → users)
├── total_value_krw (총 자산 원화 환산, encrypted)
├── breakdown (JSONB - 유형별 소계)
├── snapshot_date (date)
├── created_at
└── expires_at (1년 후 자동 삭제용)

exchange_rates
├── id (PK)
├── from_currency
├── to_currency
├── rate
├── fetched_at
└── source
```

### 6.2 Phase 2 추가 테이블

```
transactions (지출 내역)
├── id (UUID, PK)
├── user_id (FK → users)
├── date
├── description
├── amount (encrypted)
├── category (auto-classified)
├── custom_category (user override)
├── source (manual)
└── created_at

category_rules (분류 규칙)
├── id (PK)
├── user_id (FK → users)
├── keyword
├── category
└── priority
```

### 6.3 Phase 3 추가 테이블

```
watchlist (관심종목)
├── id (UUID, PK)
├── user_id (FK → users)
├── ticker
├── market (KRX, NASDAQ, etc.)
├── target_buy_price
├── target_sell_price
├── alert_threshold_pct (급등/급락 알림 기준 %)
├── notes
└── created_at

simulations (시뮬레이션 결과 저장)
├── id (UUID, PK)
├── user_id (FK → users)
├── type (dca, portfolio, scenario)
├── params (JSONB)
├── result (JSONB)
├── created_at
└── expires_at (1년 후 자동 삭제)
```

### 6.4 Phase 4 추가 테이블

```
news_articles
├── id (UUID, PK)
├── title
├── summary (AI 요약)
├── source_url
├── source_name
├── category (domestic_stock, foreign_stock, macro, tech_ai)
├── importance_score
├── published_at
├── fetched_at
├── created_at
└── expires_at (1년 후 자동 삭제)

user_news_preferences
├── id (PK)
├── user_id (FK → users)
├── keywords (JSONB array)
├── categories (JSONB array)
├── telegram_chat_id
├── alert_time (daily alert 시각)
└── created_at

telegram_alert_settings
├── id (PK)
├── user_id (FK → users)
├── chat_id
├── enable_news (boolean)
├── enable_price_alert (boolean)
├── enable_security_alert (boolean)
├── enable_monthly_report (boolean)
├── price_alert_default_pct (기본 급등/급락 기준 %)
└── created_at
```

---

## 7. API 설계 (Phase 1)

> 상세 명세: `docs/API.md`

### 7.1 FastAPI 엔드포인트

```
# 인증 ✅ 구현 완료
POST   /api/auth/login              # Google OAuth 로그인 (ID Token 서버 검증)
POST   /api/auth/refresh            # Refresh Token 로테이션
GET    /api/auth/me                 # 현재 사용자 정보
POST   /api/auth/2fa/setup          # 2FA TOTP 설정 (QR 코드 생성)
POST   /api/auth/2fa/verify         # 2FA OTP 검증
GET    /api/auth/sessions           # 활성 세션 목록 (기기별)
DELETE /api/auth/sessions/{id}      # 특정 세션 강제 로그아웃
POST   /api/auth/logout             # 로그아웃

# 자산 관리 ⬜ 미구현
GET    /api/assets                  # 내 자산 목록 (필터: type, status, group_id)
POST   /api/assets                  # 자산 추가
PUT    /api/assets/{id}             # 자산 수정
DELETE /api/assets/{id}             # 자산 삭제
POST   /api/assets/{id}/sell        # 매도 처리 (아카이브 + 실현 손익)

# 포트폴리오 그룹 ⬜ 미구현
GET    /api/groups                  # 그룹 목록
POST   /api/groups                  # 그룹 생성
PUT    /api/groups/{id}             # 그룹 수정
DELETE /api/groups/{id}             # 그룹 삭제

# 대시보드 ⬜ 미구현
GET    /api/dashboard/summary       # 자산 요약 (총액, 비중, 실현+미실현 손익)
GET    /api/dashboard/history       # 자산 변동 추이

# 시세 ⬜ 미구현
GET    /api/prices/stock/{ticker}   # 주식 현재가
GET    /api/prices/crypto/{symbol}  # 코인 현재가
GET    /api/prices/exchange-rate    # 환율
POST   /api/prices/refresh          # 시세 일괄 갱신

# 보안 ⬜ 미구현
GET    /api/security/access-logs    # 액세스 로그 조회
```

---

## 8. 보안 & 면책 & 리스크 관리

> 상세 규칙: `docs/SECURITY.md`

### 8.1 보안 — 최우선 원칙: "귀찮더라도 보안이 먼저"

**인증 (2단계 필수):**
- Google OAuth 소셜 로그인 (NextAuth.js v5)
- TOTP 기반 2FA 필수 (Google Authenticator 등)
- 첫 로그인 시 2FA 설정 강제
- 로그인 실패 5회 시 계정 잠금 (15분)

**세션 관리 (빡빡하게):**
- 30분 미사용 시 자동 로그아웃
- 기기별 세션 관리 (새 기기 로그인 시 텔레그램 알림)
- 활성 세션 목록 조회 + 원격 로그아웃 가능
- JWT Access Token 15분 + Refresh Token 7일

**데이터 보호:**
- 자산 금액 데이터 DB 암호화 (AES-256, 평문 저장 안 함)
  - 암호화 대상: quantity, purchase_price, sold_price, realized_pnl, total_value_krw, amount
- 환경변수로 민감 정보 관리 (.env.local, 절대 커밋 금지)
- HTTPS 강제 (Vercel/Railway 기본)
- API 응답에 민감 정보 최소 노출
- DB 접속 SSL 필수

**자산 금액 마스킹:**
- 대시보드에서 눈 아이콘 토글로 전체 금액 숨기기/보이기
- 마스킹 상태: 금액 → "●●●●●●원" 표시
- 마스킹 상태 localStorage에 저장 (기본: 마스킹 ON)

**액세스 로그:**
- 모든 로그인/로그아웃 기록 (IP, 기기, 시각)
- 자산 변경 작업 기록 (추가/수정/삭제/매도)
- 보안 설정 페이지에서 로그 조회 가능
- 1년 보관 후 자동 삭제

**비정상 접근 탐지 & 텔레그램 알림:**
- 새로운 기기/IP에서 로그인 시 알림
- 짧은 시간 내 다수 로그인 시도 시 알림
- 해외 IP 로그인 시 알림

**인프라 보안:**
- API Rate Limiting (SlowAPI: 100 req/min per user)
- CORS 화이트리스트 (Vercel 도메인만)
- SQL Injection 방지 (SQLAlchemy ORM, raw query 금지)
- XSS 방지 (React 기본 이스케이프 + CSP 헤더)
- 보안 헤더 (X-Content-Type-Options, X-Frame-Options 등)

### 8.2 면책 고지 (금융 데이터 정확성)
- **필수 표시**: "본 서비스는 투자 자문이 아니며, 투자 판단의 책임은 사용자에게 있습니다"
- **투자 리스크 경고**: "과거 데이터 기반 분석이며 미래 수익을 보장하지 않습니다" 상시 표시
- **데이터 신뢰도 등급**: 실시간(🟢) / 15분 지연(🟡) / 1일 배치(🟠) / 추정치(🔴)
- **데이터 소스 명시**: 각 수치 옆에 출처 + 갱신 시각 표시
- **데이터 검증**: 시세 이상치 탐지 (전일 대비 ±50% 이상 변동 시 경고)
- **첫 사용 시 면책 동의 팝업 필수**

### 8.3 투자 리스크 관리
- 매매 시그널은 항상 "참고용"으로 표시, 절대 "추천" 표현 금지
- 리스크 레벨을 색상 + 텍스트로 이중 표시 (색각 이상 고려)
- 집중 투자 경고: 단일 종목 비중 30% 이상 시 분산 투자 안내

---

## 9. 프로젝트 구조 (모노레포)

```
wealthpilot/
├── CLAUDE.md                    # Claude Code 프로젝트 지침
├── README.md
├── .github/
│   └── workflows/               # CI/CD (Phase 5)
├── frontend/                    # Next.js 앱
│   ├── src/
│   │   ├── app/                 # App Router 페이지
│   │   ├── components/          # UI 컴포넌트
│   │   │   ├── ui/              # shadcn/ui 컴포넌트
│   │   │   ├── dashboard/       # 대시보드 위젯 (미니멀 + 터미널)
│   │   │   ├── assets/          # 자산 관련
│   │   │   ├── groups/          # 포트폴리오 그룹
│   │   │   ├── analysis/        # 종목 분석 (기본+기술)
│   │   │   ├── spending/        # 지출 분석
│   │   │   ├── news/            # 뉴스 큐레이터
│   │   │   ├── security/        # 보안 설정 (2FA, 세션, 로그)
│   │   │   └── onboarding/      # 튜토리얼 위저드
│   │   ├── hooks/               # 커스텀 훅
│   │   ├── lib/                 # 유틸리티 (암호화, 포맷팅)
│   │   ├── stores/              # Zustand (모드, 마스킹, 테마)
│   │   └── types/               # TypeScript 타입
│   ├── public/
│   │   └── manifest.json        # PWA 매니페스트
│   ├── next.config.mjs
│   ├── tailwind.config.ts
│   └── package.json
├── backend/                     # FastAPI 앱
│   ├── app/
│   │   ├── main.py              # FastAPI 엔트리
│   │   ├── config.py            # 설정 (pydantic-settings)
│   │   ├── models/              # SQLAlchemy 모델
│   │   ├── schemas/             # Pydantic v2 스키마
│   │   ├── routers/             # API 라우터
│   │   ├── services/            # 비즈니스 로직
│   │   │   ├── crypto_service.py  # 암호화/복호화
│   │   │   ├── auth_service.py    # 인증 (JWT, Google 검증)
│   │   │   ├── totp_service.py    # 2FA TOTP
│   │   │   ├── security_service.py # 액세스 로그, 이상 탐지
│   │   │   ├── alert_service.py   # 텔레그램 알림
│   │   │   ├── price_service.py   # 시세 조회 (3모드) — TODO
│   │   │   ├── analysis_service.py # 종목 분석 — TODO
│   │   │   └── news_service.py    # 뉴스 수집/요약 — TODO
│   │   ├── dependencies/        # FastAPI 의존성 (auth)
│   │   ├── tasks/               # 배치 작업 (크론잡)
│   │   ├── middleware/          # Rate Limit, 보안 헤더
│   │   └── database.py          # DB 엔진/세션
│   ├── alembic/                 # DB 마이그레이션
│   ├── tests/                   # pytest 테스트
│   ├── requirements.txt
│   └── Dockerfile
├── docs/                        # 프로젝트 문서
│   ├── PRD.md                   # 이 문서
│   ├── API.md                   # API 명세
│   ├── SECURITY.md              # 보안 상세 규칙
│   ├── CONVENTIONS.md           # 코딩 컨벤션
│   └── DEPLOYMENT.md            # 배포 가이드
└── scripts/                     # 유틸리티 스크립트
    ├── seed.py                  # 테스트 데이터 시드 — TODO
    └── cleanup.py               # 1년 경과 데이터 삭제 — TODO
```

---

## 10. 비용 계획

| 항목 | 서비스 | 비용 |
|------|--------|------|
| 프론트엔드 호스팅 | Vercel (Hobby) | 무료 |
| 백엔드 호스팅 | Railway ($5 credit) 또는 Fly.io | 무료~$5/월 |
| 데이터베이스 | Supabase (Free) 또는 Neon (Free) | 무료 |
| 환율 API | ExchangeRate-API / 한국은행 | 무료 |
| 주식 시세 | yfinance + KRX | 무료 |
| 코인 시세 | CoinGecko | 무료 |
| AI 요약 (Phase 4) | Claude API (소량) | ~$5/월 |
| 텔레그램 봇 | Telegram Bot API | 무료 |
| 에러 모니터링 | Sentry (Free) | 무료 |
| **월 합계** | | **0 ~ 약 15,000원** |

---

## 11. 데이터 보관 정책

| 데이터 | 보관 기간 | 삭제 방식 |
|--------|-----------|-----------|
| 자산 스냅샷 | 1년 | 크론잡 자동 삭제 |
| 뉴스 기사 | 1년 | 크론잡 자동 삭제 |
| 시뮬레이션 결과 | 1년 | 크론잡 자동 삭제 |
| 액세스 로그 | 1년 | 크론잡 자동 삭제 |
| 매도 이력 | 무기한 | 사용자 수동 삭제 가능 |
| 사용자 자산 | 무기한 | 계정 탈퇴 시 삭제 |
| 환율 데이터 | 최근 90일 | 크론잡 자동 삭제 |

무료 DB 용량 (500MB) 관리를 위해 expires_at 필드 기반 자동 정리.

---

## 12. 성공 지표

### Phase 1 MVP 완성 기준
- [x] Google 로그인 + 2FA(OTP) 동작
- [x] 30분 미사용 자동 로그아웃 + 기기별 세션 관리
- [ ] 자산 CRUD + 매도 아카이브 동작
- [ ] 포트폴리오 그룹 생성 및 자산 할당
- [ ] 자산 총액/비중/실현+미실현 손익 대시보드
- [ ] 해외자산 원화+원래통화 병기 표시
- [ ] 금액 마스킹 토글 동작
- [ ] 환율 자동 반영
- [ ] 미니멀/터미널 모드 전환
- [ ] 시세 모드 3단계 (배치/지연/실시간)
- [ ] API 실패 시 시세만 빈칸, 나머지 정상
- [x] 액세스 로그 기록 + 조회
- [x] 비정상 접근 시 텔레그램 알림
- [x] 자산 데이터 DB 암호화
- [ ] 튜토리얼 온보딩 위저드
- [ ] Vercel + Railway 배포 완료
- [ ] PWA 홈화면 설치 가능
- [ ] 모바일 반응형 정상 동작
- [ ] API + 컴포넌트 테스트 통과

### 장기 목표
- 매일 1회 이상 본인이 실제로 사용
- Phase 4까지 2개월 내 완성
- Lighthouse Performance 90+
- 3명 이상의 외부 사용자 확보 (선택)
