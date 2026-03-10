# Phase 1 태스크 목록 & Claude Code 프롬프트 가이드

> 1주일 안에 자산 대시보드 MVP를 완성하기 위한 단계별 가이드
> 각 태스크마다 Claude Code에서 사용할 프롬프트 예시를 포함
> 버전: 2.0 (인터뷰 최종 반영)

---

## 사전 준비 (Day 0)

### 0-1. 개발 환경 확인
```
필요한 것:
- Node.js 18+ (npm 포함)
- Python 3.11+
- Git
- Docker Desktop (로컬 PostgreSQL용)
- Claude Code CLI (npm install -g @anthropic-ai/claude-code)
```

### 0-2. 프로젝트 저장소 생성
```bash
# GitHub에서 wealthpilot 레포 생성 후
git clone <repo-url>
cd wealthpilot
git checkout -b develop
git push -u origin develop
```

### 0-3. CLAUDE.md 배치
이 문서와 함께 제공된 `CLAUDE.md`를 프로젝트 루트에 복사.
Claude Code는 작업 시작 시 이 파일을 자동으로 읽어 프로젝트 컨텍스트를 파악한다.

---

## Day 1: 프로젝트 초기화 & 보안 기반

### Task 1-1. 모노레포 세팅
**Claude Code 프롬프트:**
```
wealthpilot 모노레포를 세팅해줘.

프론트엔드:
- Next.js 14 App Router + TypeScript
- Tailwind CSS + shadcn/ui 초기화
- 기본 레이아웃 (사이드바 + 메인 콘텐츠)
- PWA 설정 (next-pwa)
- Zustand 설치 (viewMode, isMasked, theme 스토어)

백엔드:
- FastAPI + Python 3.11
- SQLAlchemy 2.0 + Alembic 초기 설정
- Pydantic v2 + pydantic-settings
- uvicorn 개발 서버
- SlowAPI (Rate Limiting)

루트에 docker-compose.yml로 로컬 PostgreSQL 설정.
.env.example 파일도 프론트/백엔드 각각 만들어줘.
CLAUDE.md 파일은 이미 있으니 참고해.
```

### Task 1-2. DB 모델 & 암호화 서비스
**Claude Code 프롬프트:**
```
Phase 1에 필요한 DB 모델과 암호화 서비스를 만들어줘.

1. 암호화 서비스 (backend/app/services/crypto_service.py):
   - AES-256 암복호화 유틸
   - 환경변수에서 ENCRYPTION_KEY 읽기
   - encrypt_value(), decrypt_value() 함수

2. DB 모델 (금액 필드는 암호화 저장):
   - users: id(UUID), email, name, totp_secret(encrypted), totp_enabled, created_at, updated_at
   - sessions: id(UUID), user_id(FK), device_info, ip_address, last_active_at, expires_at, created_at
   - access_logs: id(UUID), user_id(FK), action, ip_address, device_info, is_suspicious, created_at, expires_at
   - portfolio_groups: id(UUID), user_id(FK), name, description, sort_order, created_at
   - assets: id(UUID), user_id(FK), group_id(FK nullable), type(enum: cash/domestic_stock/foreign_stock/crypto/real_estate), status(enum: active/sold/delisted), name, ticker(nullable), quantity(encrypted), purchase_price(encrypted), current_price, currency, metadata(JSONB), sold_at(nullable), sold_price(encrypted nullable), realized_pnl(encrypted nullable), created_at, updated_at
   - asset_snapshots: id(UUID), user_id(FK), total_value_krw(encrypted), breakdown(JSONB), snapshot_date, created_at, expires_at
   - exchange_rates: id, from_currency, to_currency, rate, fetched_at, source

3. Alembic 마이그레이션 생성

모든 금액 관련 필드는 Decimal 타입으로 하되, DB에 저장할 때는 encrypt_value()를 통해 암호화해줘.
```

### Task 1-3. 인증 + 2FA 설정
**Claude Code 프롬프트:**
```
인증 시스템을 설정해줘. 보안이 최우선이야.

NextAuth.js v5:
- Google OAuth 프로바이더
- JWT 세션 전략 (Access Token 15분, Refresh Token 7일)
- 로그인 페이지 (한국어)

2FA (TOTP):
- pyotp 라이브러리로 TOTP 시크릿 생성/검증
- POST /api/auth/2fa/setup — QR 코드 생성 (qrcode 라이브러리)
- POST /api/auth/2fa/verify — OTP 코드 검증
- 첫 로그인 시 2FA 미설정이면 설정 페이지로 강제 리다이렉트
- totp_secret은 DB에 암호화 저장

세션 관리:
- 30분 미사용 시 자동 로그아웃 (프론트에서 idle 감지)
- 기기별 세션 테이블 관리
- GET /api/auth/sessions — 활성 세션 목록
- DELETE /api/auth/sessions/{id} — 원격 세션 종료
- 새 기기 로그인 시 기존 세션 목록에 추가 + 텔레그램 알림 트리거

로그인 실패 5회 시 15분 계정 잠금도 구현해줘.
```

---

## Day 2: 보안 인프라 & 자산 CRUD

### Task 2-1. 액세스 로그 & 보안 미들웨어
**Claude Code 프롬프트:**
```
보안 미들웨어와 액세스 로그를 구현해줘.

1. 액세스 로그 미들웨어 (backend/app/middleware/):
   - 모든 API 요청에 대해 IP, 기기 정보, 유저 ID, 액션 기록
   - 특히 로그인/로그아웃, 자산 변경(추가/수정/삭제/매도) 기록
   - 1년 expires_at 자동 설정

2. 비정상 접근 탐지 (backend/app/services/security_service.py):
   - 새 기기/IP 로그인 감지
   - 5분 내 3회 이상 로그인 시도 감지
   - 감지 시 is_suspicious=true + 텔레그램 알림

3. 텔레그램 알림 서비스 (backend/app/services/alert_service.py):
   - 보안 알림: 새 기기 로그인, 비정상 접근, 로그인 실패 반복
   - send_telegram_message(chat_id, message) 기본 함수
   - 환경변수: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

4. Rate Limiting:
   - SlowAPI: 100 req/min per user
   - 로그인 엔드포인트: 10 req/min (브루트포스 방지)

5. 보안 헤더 미들웨어:
   - CORS (Vercel 도메인만)
   - CSP, X-Content-Type-Options, X-Frame-Options
```

### Task 2-2. 자산 관리 CRUD API
**Claude Code 프롬프트:**
```
자산 관리 CRUD API를 만들어줘. 보안 규칙 필수 적용.

엔드포인트:
- GET /api/assets — 내 자산 목록 (필터: type, status, group_id)
- POST /api/assets — 자산 추가
- PUT /api/assets/{id} — 자산 수정
- DELETE /api/assets/{id} — 자산 삭제 (soft delete 아님, 진짜 삭제)
- POST /api/assets/{id}/sell — 매도 처리

매도 처리 로직:
1. assets.status를 'sold'로 변경
2. sold_at, sold_price 기록 (암호화)
3. realized_pnl 계산: (sold_price - purchase_price) * quantity (암호화)
4. 현금 자산에 매도 대금 자동 추가 (또는 새 현금 자산 생성)
5. 매도 기록은 삭제 불가 (아카이브)

포트폴리오 그룹 API:
- GET /api/groups
- POST /api/groups
- PUT /api/groups/{id}
- DELETE /api/groups/{id} (그룹 삭제 시 소속 자산의 group_id는 null로)

모든 엔드포인트에:
- JWT 인증 필수
- 사용자 소유권 검증 (본인 자산만)
- Pydantic v2 request/response 스키마
- 금액 필드 암복호화 처리
- 액세스 로그 기록 (자산 변경 시)
- 적절한 에러 핸들링 (404, 403 등, 한국어 메시지)
```

### Task 2-3. 자산 등록 폼 & 목록 UI
**Claude Code 프롬프트:**
```
자산 등록 폼과 목록 UI를 만들어줘.

자산 등록/수정 폼:
- shadcn/ui Dialog, Form, Select, Input 사용
- 자산 유형 선택 시 해당 유형 필드만 표시:
  - 현금/예적금: 금액, 은행명, 이율
  - 국내주식: 종목명, 종목코드, 수량, 매입가
  - 해외주식/ETF: 종목명, 티커, 수량, 매입가, 통화(USD 기본)
  - 코인: 종목명, 심볼, 수량, 매입가
- 포트폴리오 그룹 선택 드롭다운 (선택사항)
- react-hook-form + zod 유효성 검증
- 성공/실패 토스트 (한국어)

자산 목록 페이지:
- 테이블: 유형 아이콘, 자산명, 그룹, 수량, 매입가, 현재가, 평가손익, 수익률
- 해외자산: 원화 + 원래 통화 병기 (예: "$150 / 195,000원")
- 수익률 양수 초록, 음수 빨강
- 금액 마스킹: Zustand isMasked=true일 때 "●●●●●●원" 표시
- 필터: 유형별 탭 + 그룹별 필터 + 상태(보유중/매도완료)
- 각 행: 수정/매도/삭제 버튼
- 매도 버튼 클릭 → 매도 다이얼로그 (수량, 매도가 입력)
- 상단: "자산 추가" 버튼, 시세 갱신 버튼

테스트:
- 자산 등록 폼 컴포넌트 테스트 (React Testing Library)
```

---

## Day 3: 시세 연동 & 환율

### Task 3-1. 시세 조회 서비스 (3모드)
**Claude Code 프롬프트:**
```
시세 조회 서비스를 만들어줘. 3가지 모드 지원.

backend/app/services/price_service.py:
1. 국내주식: yfinance (티커: "005930.KS" 형식)
2. 해외주식: yfinance (티커: "AAPL" 형식)
3. 코인: CoinGecko 무료 API
4. 환율: ExchangeRate-API 또는 한국은행 API

3가지 시세 모드:
- BATCH: 하루 1회 업데이트 (크론잡용)
- DELAYED: 5~15분 주기 자동 갱신
- REALTIME: 웹소켓 연결 (추후 유료 API 필요 가능 — 면책 고지)

각 소스별:
- 메모리 캐시 (TTL: BATCH=24h, DELAYED=15min, REALTIME=1min)
- 에러 핸들링: API 실패 시 마지막 캐시 값 반환 + "오래됨" 플래그
- Rate limiting 준수 (CoinGecko 30req/min)
- 이상치 탐지: 전일 대비 ±50% 이상 변동 시 경고 플래그

API 엔드포인트:
- GET /api/prices/stock/{ticker}
- GET /api/prices/crypto/{symbol}
- GET /api/prices/exchange-rate?from=USD&to=KRW
- POST /api/prices/refresh (전체 보유 종목 시세 일괄 갱신)
- GET /api/prices/mode — 현재 시세 모드 조회
- PUT /api/prices/mode — 시세 모드 변경

Sentry 연동: API 실패 시 Sentry에 기록 + 텔레그램 알림.
pytest 테스트도 작성해줘 (mock API 사용).
```

### Task 3-2. 시세 자동 반영 & 환율 처리
**Claude Code 프롬프트:**
```
시세 자동 갱신과 환율 처리 로직을 만들어줘.

POST /api/prices/refresh 호출 시:
1. 사용자의 모든 active 자산 조회
2. 각 자산의 ticker/symbol로 현재가 조회
3. assets.current_price 업데이트
4. 환율 적용하여 원화 환산가 계산
5. 결과 요약 반환 (성공/실패 건수, 갱신 시각)

환율 변환:
- 해외자산은 항상 원화 + 원래 통화 병기
- exchange_rates 테이블에 최신 환율 캐시
- 환율 소스 + 갱신 시각 표시

프론트엔드:
- "시세 갱신" 버튼 (로딩 스피너)
- "마지막 갱신: YYYY-MM-DD HH:mm" 표시
- 데이터 신뢰도 등급: 🟢실시간 / 🟡15분지연 / 🟠1일배치 / 🔴추정치
- API 실패 시: 시세 부분만 빈칸 + "데이터를 가져올 수 없습니다" 작은 텍스트
- 나머지 UI는 정상 동작 유지
```

---

## Day 4: 대시보드

### Task 4-1. 대시보드 API
**Claude Code 프롬프트:**
```
대시보드용 API를 만들어줘.

GET /api/dashboard/summary:
- 총 자산 (원화 환산, 암호화 복호화 후 계산)
- 자산 유형별 소계 및 비중(%)
- 포트폴리오 그룹별 소계 및 비중(%)
- 총 수익률:
  - 합산 (실현 + 미실현) — 기본 표시
  - 실현 손익 (매도 완료분 합계)
  - 미실현 손익 (보유 중 평가손익)
- 전일 대비 변동 금액/비율

GET /api/dashboard/history?period=1M|3M|6M|1Y:
- asset_snapshots에서 기간별 데이터
- 일별 총 자산 추이
- 유형별 추이 (breakdown)

POST /api/dashboard/snapshot:
- 현재 자산 상태를 스냅샷으로 저장 (암호화)
- expires_at = created_at + 1년
- 하루 1회 크론잡으로 자동 실행 예정

응답 데이터에서 금액은 복호화하여 반환하되,
프론트에서 isMasked 상태에 따라 마스킹 처리.
```

### Task 4-2. 미니멀 모드 대시보드
**Claude Code 프롬프트:**
```
미니멀 모드 대시보드를 만들어줘. Linear/Vercel 스타일로 깔끔하게.

레이아웃:
1. 상단: 총 자산 카드 (큰 숫자 + 전일 대비 변동)
   - 수익률 탭: [합산 | 실현 | 미실현]
2. 중단 좌: 자산 비중 도넛차트 (Recharts PieChart)
   - 유형별 / 그룹별 전환 가능
3. 중단 우: 자산 변동 추이 라인차트 (기간 선택: 1M/3M/6M/1Y)
4. 하단: 포트폴리오 그룹별 요약 카드

디자인:
- 다크모드 기본, 트렌디한 느낌
- shadcn/ui Card 활용
- 해외자산: "$150 / 195,000원" 병기
- 수익률: 양수 초록(+), 음수 빨강(-)
- 금액 마스킹: 👁 토글 → "●●●●●●원"
- 데이터 갱신 시각 + 신뢰도 등급 표시
- 면책 문구: 화면 하단에 작은 글씨

SWR 또는 React Query로 데이터 페칭.
React Testing Library로 컴포넌트 테스트도 작성.
```

### Task 4-3. 터미널 모드 대시보드
**Claude Code 프롬프트:**
```
트레이딩 터미널 스타일 대시보드를 만들어줘.

미니멀 모드와 같은 데이터, 다른 레이아웃:
1. 좌측: 보유 자산 시세 테이블 (가격, 변동, 변동률, 수량, 평가액)
   - 해외자산은 USD + KRW 병기
   - 수익률 색상 (초록/빨강)
2. 중앙: 메인 차트 영역 (TradingView Lightweight Charts 또는 큰 Recharts)
3. 우측: 자산 비중 + 요약 통계 + 그룹별 소계
4. 하단: 최근 거래/변동 로그 (매도 이력 포함)

디자인:
- 어두운 배경, 녹색/빨강 강조
- 모노스페이스 폰트 (숫자)
- 작은 폰트로 높은 정보 밀도
- 그리드 레이아웃 (CSS Grid)
- 데스크톱 전용 (모바일에서는 미니멀 모드로 전환)

모드 전환:
- 상단 네비게이션에 [미니멀 | 터미널] 토글 (shadcn/ui Switch)
- Zustand viewMode 상태로 관리
- localStorage에 선호 모드 저장
```

---

## Day 5: 온보딩 & 반응형 & PWA

### Task 5-1. 튜토리얼 온보딩 위저드
**Claude Code 프롬프트:**
```
첫 가입 사용자를 위한 튜토리얼 온보딩 위저드를 만들어줘.

플로우:
1. 환영 화면: "WealthPilot에 오신 것을 환영합니다" + 서비스 소개
2. 면책 동의: 투자 리스크 + 데이터 정확성 면책 고지 동의 (필수)
3. 2FA 설정: Google Authenticator QR 스캔 + OTP 확인 (필수)
4. 자산 유형 선택: "어떤 자산을 보유하고 계세요?" (복수 선택)
   - 선택한 유형만 다음 단계에서 안내
5. 자산 등록 가이드: 선택한 유형별로 입력 방법 안내 + 첫 자산 등록
6. 대시보드 도착: "설정 완료! 자산 현황을 확인해보세요"

UI:
- 스텝 인디케이터 (1/6, 2/6...)
- 스킵 가능 (단, 면책 동의와 2FA는 스킵 불가)
- 나중에 다시 볼 수 있는 "도움말" 메뉴
- shadcn/ui Stepper 또는 직접 구현

사용자 DB에 onboarding_completed 플래그 추가.
미완료 시 로그인 후 항상 위저드로 리다이렉트.
```

### Task 5-2. 모바일 반응형 & PWA
**Claude Code 프롬프트:**
```
모바일 반응형과 PWA를 완성해줘.

반응형:
- 사이드바: 모바일에서 햄버거 메뉴
- 대시보드 카드: 모바일 1컬럼 스택
- 터미널 모드: 모바일에서 자동으로 미니멀 모드 전환
- 차트: 터치 친화적, 스와이프로 기간 변경
- 테이블: 모바일에서 카드 형태 변환
- 금액 마스킹 토글: 모바일에서도 쉽게 접근

PWA:
- manifest.json (앱 이름: WealthPilot, 테마: 다크)
- Service Worker 기본 캐싱
- 아이콘 (192x192, 512x512)
- iOS Safari 메타 태그
- 오프라인 폴백 페이지

Tailwind 브레이크포인트: sm(640) / md(768) / lg(1024) / xl(1280).
```

---

## Day 6: 배포 & 연결

### Task 6-1. 백엔드 배포 (Railway)
**Claude Code 프롬프트:**
```
FastAPI 백엔드를 Railway에 배포하기 위한 설정을 만들어줘.

1. Dockerfile (Python 3.11-slim 기반)
2. 환경변수 목록:
   - DATABASE_URL
   - ENCRYPTION_KEY (AES-256)
   - JWT_SECRET
   - NEXTAUTH_SECRET
   - CORS_ORIGINS (Vercel URL)
   - GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
   - TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
   - SENTRY_DSN
3. healthcheck: GET /health
4. CORS 설정 (Vercel xxx.vercel.app 도메인만)
5. Sentry FastAPI 통합 설정
6. 배포 순서 + CLI 명령어 안내
```

### Task 6-2. 프론트엔드 배포 (Vercel)
**Claude Code 프롬프트:**
```
Next.js 프론트엔드를 Vercel에 배포하기 위한 설정을 확인해줘.

1. 환경변수:
   - NEXT_PUBLIC_API_URL (Railway 백엔드 URL)
   - NEXTAUTH_URL (xxx.vercel.app)
   - NEXTAUTH_SECRET
   - Google OAuth 키
2. next.config.js: API 프록시 rewrites
3. 빌드 확인 (npm run build 에러 없는지)
4. Sentry Next.js 통합 설정
5. 보안 헤더 (next.config.js headers)
6. 배포 후 체크리스트
```

### Task 6-3. DB 연결 & 시드 데이터
**Claude Code 프롬프트:**
```
Supabase PostgreSQL을 연결하고 테스트 데이터를 넣어줘.

1. Supabase 프로젝트 연결 설정 안내 (SSL 필수)
2. Alembic으로 프로덕션 DB 마이그레이션
3. 시드 스크립트 (scripts/seed.py):
   - 테스트 유저 1명 (2FA 설정 완료 상태)
   - 포트폴리오 그룹: "장기투자", "단기트레이딩"
   - 자산 샘플 (모두 암호화 저장):
     - 현금: 예적금 2건
     - 국내주식: 삼성전자, SK하이닉스, 네이버 (장기투자 그룹)
     - 해외주식: AAPL, TSLA (장기투자 그룹)
     - 코인: BTC, ETH (단기트레이딩 그룹)
   - 매도 완료 자산 1건 (아카이브 테스트용)
   - asset_snapshots 30일치
   - exchange_rates 최신 환율
   - access_logs 샘플 5건
```

---

## Day 7: 통합 테스트 & 마무리

### Task 7-1. 테스트 작성
**Claude Code 프롬프트:**
```
Phase 1 핵심 기능에 대한 테스트를 작성해줘.

API 테스트 (pytest):
- 인증: 로그인, 2FA 검증, 세션 관리, 30분 만료
- 자산 CRUD: 추가, 수정, 삭제, 매도 아카이브
- 포트폴리오 그룹: CRUD + 자산 할당
- 대시보드: summary (실현+미실현 분리), history
- 시세: 갱신, 모드 전환, 캐시 동작
- 보안: 타인 자산 접근 차단, Rate Limiting, 암복호화

컴포넌트 테스트 (React Testing Library):
- 자산 등록 폼: 유형별 필드 표시, 유효성 검증
- 대시보드 카드: 금액 마스킹 토글, 수익률 색상
- 모드 전환: 미니멀 ↔ 터미널
- 온보딩 위저드: 스텝 진행, 필수 스텝 스킵 불가
```

### Task 7-2. 통합 테스트 & 버그 수정
**Claude Code 프롬프트:**
```
Phase 1 전체를 점검하고 버그를 수정해줘.

체크리스트:
1. Google 로그인 → 2FA 설정 → 온보딩 → 대시보드 플로우
2. 자산 추가 → 시세 갱신 → 대시보드 확인
3. 매도 처리 → 실현 손익 기록 → 현금 반영 → 매도 이력 확인
4. 포트폴리오 그룹 생성 → 자산 할당 → 그룹별 수익률
5. 모드 전환 (미니멀 ↔ 터미널) 정상 동작
6. 금액 마스킹 토글 동작
7. 해외자산 원화+달러 병기 표시
8. 수익률 탭 (합산/실현/미실현) 전환
9. 다크모드/라이트모드 전환
10. 모바일 반응형 + PWA 홈화면 설치
11. 30분 자동 로그아웃 동작
12. 기기별 세션 관리 (세션 목록, 원격 로그아웃)
13. 액세스 로그 기록 및 조회
14. API 실패 시 시세만 빈칸 동작
15. 데이터 암호화 검증 (DB 직접 조회 시 평문 안 보이는지)
16. Sentry 에러 기록 동작
17. 텔레그램 보안 알림 동작
```

### Task 7-3. README & 문서 정리
**Claude Code 프롬프트:**
```
프로젝트 README.md를 작성해줘.

포함할 내용:
1. 프로젝트 소개 (한국어)
2. 기술 스택 배지
3. 주요 기능 요약
4. 보안 특징 강조
5. 스크린샷 자리 (추후 추가)
6. 로컬 개발 환경 설정 (step by step)
7. 환경변수 설정 안내 (ENCRYPTION_KEY 생성 방법 포함)
8. Git Flow 브랜치 전략 안내
9. 배포 방법
10. 프로젝트 구조 설명
11. Phase별 로드맵
12. 라이선스

docs/DEPLOYMENT.md에 배포 상세 가이드도 작성.
docs/API.md에 API 명세도 정리.
```

---

## Claude Code 활용 팁

### 프로젝트 컨텍스트 유지
```bash
# 프로젝트 루트에서 Claude Code 실행 — CLAUDE.md 자동 인식
cd wealthpilot
claude
```

### Git Flow와 Claude Code
```bash
# 1. develop에서 feature 브랜치 생성
git checkout develop
git checkout -b feature/asset-crud

# 2. Claude Code로 구현
claude "자산 CRUD API를 만들어줘..."

# 3. 직접 코드 리뷰 (중요!)
git diff  # 변경사항 확인

# 4. 빌드 & 테스트
cd frontend && npm run build && npm test
cd backend && pytest

# 5. 커밋 (Conventional Commits)
git add -A && git commit -m "feat: 자산 CRUD API 구현"

# 6. develop에 머지
git checkout develop && git merge feature/asset-crud

# 7. 릴리즈 시 main에 머지
git checkout main && git merge develop
git tag v0.1.0
```

### 효과적인 프롬프트 작성법
1. **구체적인 파일 경로**: "backend/app/services/에 price_service.py를 만들어줘"
2. **기존 코드 참조**: "현재 AssetCard 컴포넌트를 수정해서..."
3. **보안 규칙 리마인드**: "CLAUDE.md의 보안 규칙에 따라서..."
4. **테스트 포함 요청**: "pytest 테스트도 함께 작성해줘"
5. **에러 공유**: 에러 메시지 복사 후 "이 에러를 수정해줘"

### /compact 명령 활용
```
# 대화가 길어지면 컨텍스트 압축
/compact
```

### 코드 리뷰 체크포인트
Claude Code 작업 후 반드시 확인:
- [ ] 금액 필드가 crypto_service로 암호화되고 있는지
- [ ] API에 인증 미들웨어가 적용되었는지
- [ ] 사용자 소유권 검증이 있는지
- [ ] 에러 메시지가 한국어인지
- [ ] 테스트가 통과하는지

---

## Phase 2 미리보기

Phase 1 완성 후 Phase 2(지출 패턴 분석기) 상세 태스크 생성 예정.
주요 작업: 수동 입력 폼 → 카테고리 분류 규칙 → 지출 대시보드 → 인사이트 엔진
