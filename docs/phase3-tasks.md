# Phase 3 태스크 목록: 투자 종목 분석기

> 종목의 가치를 평가하고 매매 판단을 돕는 분석 기능 구현
> 기본적 분석, 기술적 분석, 매매 시그널, 관심종목, 포트폴리오 시뮬레이션 포함
> 모든 분석 화면에 투자 면책 고지 필수, 데이터 소스/신뢰도 표시 필수


---

## Task 의존성

```
3-1 (DB) → 3-2 (스키마) → 3-3 (분석 서비스) ──→ 3-4 (라우터)
                        → 3-5 (시뮬레이션)  ──→  ↓
                                              3-6 (FE 타입/훅) → 3-7 (분석 UI)
                                                               → 3-8 (관심종목/시뮬 UI)
3-9 (트랜잭션 분리)
3-10 (자동매매 UX 재설계 + API 점검)
3-11 (자동 종목 탐색 전략) — 독립 태스크, 기존 전략 엔진 + KIS API 기반
```
- 3-3과 3-5는 병렬 가능
- 3-7과 3-8은 병렬 가능
- 3-11은 독립적으로 진행 가능 (기존 모델/서비스 확장)

---

## Task 3-1: DB 모델 + Alembic 마이그레이션

**새 파일**: `backend/app/models/analysis.py`
- `Watchlist` 모델: id(UUID PK), user_id(FK), ticker, market, target_buy_price(AES-256 암호화), target_sell_price(AES-256 암호화), alert_threshold_pct(Numeric, 비암호화), notes, created_at, updated_at
  - UniqueConstraint: `(user_id, ticker, market)`
- `Simulation` 모델: id(UUID PK), user_id(FK), type(Enum: dca/portfolio/scenario), params(JSONB), result(JSONB), created_at, expires_at(30일 후)

**수정 파일**:
- `backend/app/models/__init__.py` — 새 모델 import 추가
- `backend/app/services/security_service.py` — AccessAction 상수 추가

**패턴 참조**: `backend/app/models/trading.py` (UUID PK, 암호화 Text 필드, Enum, JSONB)

**마이그레이션**: `alembic revision --autogenerate -m "add_watchlist_and_simulations"`

**검증**: `alembic upgrade head` 성공, 암호화 필드 round-trip 테스트

---

## Task 3-2: Pydantic 스키마

**새 파일**: `backend/app/schemas/analysis.py`
- Enums: `ValuationSignal`, `TradingSignalAction`, `SimulationType`, `MarketType`
- Response 스키마: `FundamentalAnalysisResponse`, `TechnicalAnalysisResponse`, `TradingSignalsResponse`
- Watchlist 스키마: `WatchlistCreate`, `WatchlistUpdate`, `WatchlistResponse` + `watchlist_to_response()` 복호화 변환
- Simulation 스키마: `SimulationRequest`, `SimulationResponse`
- 면책 고지 상수: `INVESTMENT_DISCLAIMER_KO`

**패턴 참조**: `backend/app/schemas/trading.py` (Pydantic v2, `*_to_response()` 복호화 패턴)

**검증**: 스키마 validation 단위 테스트

---

## Task 3-3: 종목 분석 서비스 (기본적 + 기술적 분석)

**새 파일**: `backend/app/services/stock_analysis_service.py`
- `get_fundamental_analysis(ticker, market)`: yfinance `Ticker.info` → PER, PBR, ROE, EPS, 섹터 평균, DCF 적정가, 평가 시그널(green/yellow/red)
- `get_technical_analysis(ticker, market)`: yfinance `Ticker.history(period="1y")` → RSI, MACD, 볼린저밴드, SMA(5/20/60/120), 지지/저항선
- `get_trading_signals(ticker, market)`: 기본적+기술적 분석 종합 → 매수/매도/관망, 신뢰도, 리스크 레벨

**재사용 코드**:
- `backend/app/services/trading_strategy.py`의 `_ema()`, `_rsi()` 함수 import
- `_sma()` 함수를 `trading_strategy.py`에 추가 (하위 호환)
- `price_service.py`의 `asyncio.to_thread()` 패턴으로 yfinance 비동기 래핑
- 15분 TTL 인메모리 캐시 (price_service 캐시 패턴)

**검증**: mocked yfinance로 지표 계산 정확성 pytest

---

## Task 3-4: Watchlist 서비스 + API 라우터

**새 파일**:
- `backend/app/services/watchlist_service.py` — CRUD + 알림 체크
- `backend/app/routers/analysis.py` — 8개 엔드포인트:
  ```
  GET    /api/analysis/stock/{ticker}           # 기본적 분석
  GET    /api/analysis/stock/{ticker}/technical  # 기술적 분석
  GET    /api/analysis/stock/{ticker}/signals    # 매매 시그널
  POST   /api/analysis/simulate                  # 시뮬레이션
  GET    /api/analysis/watchlist                  # 관심종목 목록
  POST   /api/analysis/watchlist                  # 추가
  PUT    /api/analysis/watchlist/{id}             # 수정
  DELETE /api/analysis/watchlist/{id}             # 삭제
  ```

**수정 파일**: `backend/app/main.py` — 라우터 등록

**보안**: 전 엔드포인트 JWT 인증 + 소유권 검증 + 액세스 로그. target_buy/sell_price는 `crypto_service.py`로 암복호화.

**검증**: 8개 엔드포인트 pytest + 소유권 위반 테스트

---

## Task 3-5: 시뮬레이션 서비스

**새 파일**: `backend/app/services/simulation_service.py`
- `run_dca_simulation(params)`: 월적립 시뮬, yfinance 과거 데이터 기반 → 월별 breakdown, 총투자/최종가치/수익률
- `run_portfolio_simulation(params)`: 다종목 포트폴리오 리밸런싱 시뮬 → 성과/리밸런싱 이벤트
- `run_scenario_simulation(params)`: 진입가/수량/목표가/손절가 → 잠재 수익/손실/위험보상비

**수정**: `backend/app/routers/analysis.py`의 `POST /simulate` 엔드포인트에 연결

**검증**: 알려진 과거 데이터로 DCA 계산 정확성 테스트

---

## Task 3-6: 프론트엔드 타입 + 훅 + API 연동

**수정 파일**: `frontend/src/types/index.ts` — Phase 3 타입 추가 (FundamentalAnalysis, TechnicalAnalysis, TradingSignals, WatchlistItem, SimulationResult + Api variant + 변환 함수)

**새 파일**:
- `frontend/src/hooks/useStockAnalysis.ts` — fundamental/technical/signals 병렬 fetch
- `frontend/src/hooks/useWatchlist.ts` — CRUD 훅
- `frontend/src/hooks/useSimulation.ts` — 시뮬레이션 실행 훅

**패턴 참조**: `frontend/src/hooks/useAssets.ts` (SWR + session accessToken 패턴)

---

## Task 3-7: 분석 UI 컴포넌트

**새 라우트**:
- `frontend/src/app/(dashboard)/analysis/page.tsx` — 종목 검색 + 목록
- `frontend/src/app/(dashboard)/analysis/[ticker]/page.tsx` — 종목 상세 (탭 구조)

**새 컴포넌트**: `frontend/src/components/analysis/`
- `TickerSearch.tsx` — debounced 종목 검색
- `InvestmentDisclaimer.tsx` — 면책 고지 배너 (모든 분석 화면 필수)
- `DataFreshnessBadge.tsx` — 데이터 소스/시각 뱃지
- `FundamentalCard.tsx` — PER/PBR/ROE/EPS 카드 + 섹터 비교 + DCF + 평가 시그널
- `TechnicalChart.tsx` — Recharts 차트 (이동평균선, 볼린저밴드, RSI, MACD)
- `SignalCard.tsx` — 매매 시그널 카드 (매수/매도/관망 + 신뢰도 + 리스크)
- `ValuationGauge.tsx` — 적정가 대비 현재가 게이지

**패턴 참조**: `AssetTrendChart.tsx` (Recharts), shadcn Card/Badge/Tabs

**보안**: `isMasked` 상태에 따라 금액 마스킹 적용

---

## Task 3-8: 관심종목 UI + 시뮬레이션 UI + 텔레그램 알림

**새 라우트**: `frontend/src/app/(dashboard)/watchlist/page.tsx`

**새 컴포넌트**:
- `WatchlistTable.tsx` — 관심종목 테이블 (ticker, 현재가, 목표가, 알림기준, 메모, 액션)
- `WatchlistAddDialog.tsx` — 추가/수정 다이얼로그 (react-hook-form + zod)
- `DCASimulator.tsx` — DCA 시뮬레이터 폼 + 결과 차트
- `PortfolioSimulator.tsx` — 포트폴리오 리밸런싱 시뮬레이터
- `ScenarioCalculator.tsx` — 시나리오 계산기

**새 파일**: `backend/app/tasks/watchlist_alert_task.py` — 관심종목 알림 체크 함수 (크론잡용)

**수정 파일**:
- `frontend/src/config/navigation.ts` — "관심종목" 메뉴 추가 (`/watchlist`, Star 아이콘)
- `backend/app/services/alert_service.py` — 관심종목 알림 템플릿 추가

---

## Task 3-9: 분석 라우터 트랜잭션 분리 리팩토링

**수정 파일**: `backend/app/routers/analysis.py`

현재 모든 엔드포인트(simulate, add_watchlist, modify_watchlist, remove_watchlist)에서 메인 비즈니스 로직(시뮬레이션 저장, 관심종목 CRUD)과 액세스 로그(`log_access`)가 동일 트랜잭션으로 commit된다. 액세스 로그 INSERT의 DB 레벨 오류가 메인 데이터까지 롤백시킬 수 있다.

**변경 내용**:
- 메인 비즈니스 로직 완료 후 즉시 `db.commit()` (데이터 보존 확정)
- `log_access`는 별도 try/except + rollback/commit으로 분리 (실패 시 메인 데이터에 영향 없음)
- 라우터 내 전체 엔드포인트에 일괄 적용하여 패턴 통일

**검증**: 기존 테스트 전체 통과 확인

---

## Task 3-10: 자동매매 UI + API 통합 점검 및 수정

자동매매(trading) 관련 프론트엔드 UI와 백엔드 API를 하나씩 점검하며 실제 동작하도록 수정한다.

### 점검 대상 API 엔드포인트

| # | 엔드포인트 | 설명 |
|---|---|---|
| 1 | `POST /api/trading/accounts` | 계좌 등록 (KIS 잔액 자동 조회) |
| 2 | `GET /api/trading/accounts` | 계좌 목록 조회 |
| 3 | `DELETE /api/trading/accounts/{id}` | 계좌 비활성화 |
| 4 | `GET /api/trading/accounts/{id}/balance` | KIS 실시간 잔고 조회 |
| 5 | `POST /api/trading/strategies` | 전략 생성 |
| 6 | `GET /api/trading/strategies` | 전략 목록 조회 |
| 7 | `PUT /api/trading/strategies/{id}` | 전략 수정 |
| 8 | `POST /api/trading/strategies/{id}/schedule/start` | 스케줄 시작 |
| 9 | `POST /api/trading/strategies/{id}/schedule/stop` | 스케줄 중지 |
| 10 | `POST /api/trading/strategies/{id}/run-now` | 즉시 실행 |
| 11 | `GET /api/trading/strategies/{id}/schedule/status` | 스케줄 상태 |
| 12 | `GET /api/trading/orders` | 주문 내역 조회 |
| 13 | `GET /api/trading/positions` | 포지션 조회 |
| 14 | `GET /api/trading/performance` | 수익률 조회 |

### 점검 대상 프론트엔드 컴포넌트

- `AccountFormDialog.tsx` — 계좌 등록 다이얼로그
- `AccountsStrategiesTab.tsx` — 계좌/전략 탭
- `StrategyFormDialog.tsx` — 전략 생성/수정 다이얼로그
- `OrdersTab.tsx` / `PositionsTab.tsx` / `PerformanceTab.tsx` — 주문/포지션/수익률 탭
- `useTrading.ts` — API 호출 훅
- `api.ts` — fetch 유틸리티

### 알려진 이슈

1. **계좌 삭제 (DELETE)**: 백엔드 204 정상 반환되나 프론트에서 `Fetch failed` 발생. `api.ts`에서 body 없는 요청의 `Content-Type` 헤더 제거했으나 미해결 — 브라우저 네트워크 탭 상세 분석 필요
2. **계좌 생성 시 초기자금**: KIS API 자동 조회로 변경 완료 — 실제 KIS 연동 테스트 필요
3. **CORS / 네트워크**: 로컬 IP(`100.80.76.62`) 접근 시 `--host 0.0.0.0` 필수, CORS_ORIGINS에 해당 IP 추가 필요

### 점검 방법

각 항목을 아래 순서로 진행:
1. 브라우저에서 UI 조작 → 정상 동작 확인
2. 실패 시 브라우저 Network 탭에서 요청/응답 확인
3. 백엔드 로그 대조
4. 원인 파악 후 코드 수정
5. 수정 후 재테스트

**검증**: 모든 API 엔드포인트 브라우저에서 정상 동작 + 기존 pytest 통과

---

## Task 3-11: 자동 종목 탐색 전략 (Auto Screener)

기존 자동매매는 사용자가 대상 종목(`target_tickers`)을 직접 지정해야 한다. 종목을 지정하지 않아도 알고리즘이 유니버스(종목 풀)에서 조건에 맞는 종목을 자동으로 찾아 매매하는 전략 타입을 추가한다.

### 핵심 개념

```
[유니버스 정의]          [스크리닝 조건]           [매매 판단]
KOSPI 200 등 종목 풀 → 거래량·RSI·이평선 필터 → 기존 전략 엔진 평가 → 주문
```

- 기존 `ma_crossover`, `mean_reversion`은 **사용자 지정 종목**만 분석
- 새 `auto_screener`는 **유니버스 전체를 스캔** → 조건 충족 종목만 전략 엔진에 전달

### 유니버스 종류

| 유니버스 | 종목 수 | 스캔 소요시간 (예상) | 비고 |
|---------|---------|---------------------|------|
| `kospi50` | ~50 | ~3초 | 시가총액 상위 50 |
| `kospi200` | ~200 | ~10초 | KOSPI 200 지수 구성종목 |
| `kosdaq150` | ~150 | ~8초 | KOSDAQ 150 지수 구성종목 |
| `custom` | 사용자 정의 | 종목 수에 비례 | 사용자가 종목 풀 직접 구성 |

- KIS API 초당 호출 제한(20회/초)을 고려한 소요시간
- 유니버스 구성종목은 정적 JSON으로 관리 (월 1회 수동 갱신 또는 KIS 업종 API 활용)

### 스크리닝 조건 (params_json)

```json
{
  "universe": "kospi200",
  "min_volume": 100000,
  "volume_surge_ratio": 2.0,
  "rsi_oversold": 30,
  "rsi_overbought": 70,
  "ma_cross_periods": [5, 20],
  "max_candidates": 5,
  "eval_strategy": "ma_crossover",
  "eval_params": {
    "fast_period": 5,
    "slow_period": 20,
    "rsi_period": 14
  }
}
```

- `universe`: 스캔 대상 종목 풀
- `min_volume`: 최소 거래량 (유동성 필터)
- `volume_surge_ratio`: 평균 대비 거래량 급증 비율 (선택)
- `rsi_oversold` / `rsi_overbought`: RSI 기반 사전 필터
- `ma_cross_periods`: 이동평균 교차 사전 필터 (선택)
- `max_candidates`: 스크리닝 후 최대 후보 수 (API 호출 절약)
- `eval_strategy`: 후보 종목에 적용할 매매 전략 (기존 전략 재활용)
- `eval_params`: 매매 전략 파라미터

### 매매 사이클 흐름 (auto_screener)

```
1. 유니버스 종목 목록 로드
2. 1차 스크리닝: KIS 현재가 API로 거래량·가격 필터
   - API 호출 최적화: 배치 조회 또는 rate-limit 준수 sleep
3. 후보 종목 추출 (max_candidates개)
4. 2차 분석: 후보별 일봉 시세 조회 → 기존 전략 엔진(eval_strategy)으로 매매 판단
5. 리스크 관리: 기존 RiskManager 그대로 적용
6. 주문 실행
```

### 변경 대상

#### 백엔드

**수정 파일**:
- `backend/app/models/trading.py`
  - `StrategyType` enum에 `AUTO_SCREENER = "auto_screener"` 추가
  - `target_tickers` 컬럼: `default=list` 유지 (빈 리스트 허용, nullable 변경 불필요)
- `backend/app/schemas/trading.py`
  - `TradingStrategyCreate.target_tickers`: validator 변경 — `auto_screener`일 때 빈 리스트 허용
  - `StrategyType` Pydantic enum에 `auto_screener` 추가
- `backend/app/services/trading_strategy.py`
  - `create_strategy()`: `auto_screener` 분기 추가
- `backend/app/tasks/trading_cycle.py`
  - `_run_cycle()`: `strategy_type == auto_screener`일 때 스크리닝 → 후보 추출 → 기존 평가 파이프라인으로 전달

**새 파일**:
- `backend/app/services/stock_screener.py`
  - `StockScreener` 클래스: 유니버스 로드, 1차 스크리닝(거래량·RSI·이평선), 후보 반환
  - `load_universe(name: str) -> list[str]`: 유니버스 종목 코드 목록 반환
  - `screen(kis: KISClient, universe: list[str], params: dict) -> list[str]`: 스크리닝 실행
- `backend/app/data/universes/kospi50.json` — 종목 코드 목록
- `backend/app/data/universes/kospi200.json` — 종목 코드 목록
- `backend/app/data/universes/kosdaq150.json` — 종목 코드 목록

**마이그레이션**: `alembic revision --autogenerate -m "add_auto_screener_strategy_type"`

#### 프론트엔드

**수정 파일**:
- `frontend/src/types/trading.ts`
  - `StrategyType`에 `"auto_screener"` 추가
  - `strategyTypeLabels`에 `auto_screener: "자동 종목 탐색"` 추가
- `frontend/src/components/trading/StrategyFormDialog.tsx`
  - `auto_screener` 선택 시: `target_tickers` 입력 숨기기, 유니버스 선택 드롭다운 + 스크리닝 파라미터 폼 표시
  - `DEFAULT_PARAMS`에 `auto_screener` 기본값 추가

### KIS API 호출 최적화

스크리닝은 대량의 API 호출이 발생하므로 최적화 필수:

1. **Rate-limit 준수**: KIS 초당 20건 제한 → `asyncio.Semaphore(15)` + 안전 마진
2. **병렬 배치**: `asyncio.gather()`로 15건씩 병렬 호출 → 50종목 ~4초
3. **캐싱**: 동일 사이클 내 중복 종목 조회 방지 (인메모리)
4. **조기 종료**: `max_candidates` 도달 시 나머지 스캔 중단

### 리스크 관리

기존 `RiskManager` 그대로 적용:
- 최대 포지션 수 제한
- 종목당 최대 투자 비율
- 일일 손실 한도
- 손절 라인

추가 고려:
- `auto_screener`는 종목 분산이 넓어질 수 있으므로 `max_positions` 파라미터 중요
- 스크리닝 결과 로그: 어떤 종목이 후보로 올라왔고 왜 선택/제외됐는지 기록

### 검증

1. **유닛 테스트**: `StockScreener` 스크리닝 로직 — mocked KIS 데이터
2. **통합 테스트**: `auto_screener` 전략 생성 → 사이클 실행 → 주문 생성 확인
3. **API 호출 카운트**: 유니버스 크기 대비 실제 KIS API 호출 수 검증
4. **프론트엔드**: `StrategyFormDialog`에서 `auto_screener` 선택 시 UI 전환 확인

---

## 검증 계획

1. **백엔드 단위 테스트**: `pytest -x -q --tb=short` (각 Task마다)
2. **API 통합 테스트**: 8개 엔드포인트 호출 + 응답 스키마 검증
3. **프론트엔드 테스트**: RTL로 컴포넌트 렌더링 + 면책 고지 표시 확인
4. **E2E 수동 테스트**: 종목 검색 → 분석 화면 확인 → 관심종목 CRUD → 시뮬레이션 실행
5. **보안 체크**: 암호화 round-trip, 소유권 검증, isMasked 동작
