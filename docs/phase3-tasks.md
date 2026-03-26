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
```
- 3-3과 3-5는 병렬 가능
- 3-7과 3-8은 병렬 가능

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

## 검증 계획

1. **백엔드 단위 테스트**: `pytest -x -q --tb=short` (각 Task마다)
2. **API 통합 테스트**: 8개 엔드포인트 호출 + 응답 스키마 검증
3. **프론트엔드 테스트**: RTL로 컴포넌트 렌더링 + 면책 고지 표시 확인
4. **E2E 수동 테스트**: 종목 검색 → 분석 화면 확인 → 관심종목 CRUD → 시뮬레이션 실행
5. **보안 체크**: 암호화 round-trip, 소유권 검증, isMasked 동작
