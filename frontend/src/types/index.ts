// 자산 유형 — 단일 소스에서 타입과 런타임 Set을 모두 파생
export const ASSET_TYPE_VALUES = [
  "cash",
  "domestic_stock",
  "foreign_stock",
  "crypto",
  "real_estate",
] as const;

export type AssetType = (typeof ASSET_TYPE_VALUES)[number];

// 자산 상태
export type AssetStatus = "active" | "sold" | "delisted";

// 자산 출처 (manual: 수동 등록 / kis: KIS 잔고 자동 동기화)
export type AssetSource = "manual" | "kis";

// 통화 (법정통화만 — 코인은 type='crypto'로 식별)
export type Currency = "KRW" | "USD" | "EUR" | "JPY";

// 자산
export interface Asset {
  id: string;
  groupId: string | null;
  type: AssetType;
  status: AssetStatus;
  name: string;
  ticker: string | null;
  quantity: number;
  purchasePrice: number;
  currentPrice: number | null;
  currency: Currency;
  metadata: Record<string, unknown>;
  soldAt: string | null;
  soldPrice: number | null;
  realizedPnl: number | null;
  source: AssetSource;
  tradingAccountId: string | null;
  externalTicker: string | null;
  lastSyncedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

// 포트폴리오 그룹
export interface PortfolioGroup {
  id: string;
  userId?: string;
  name: string;
  description: string | null;
  sortOrder: number;
  createdAt: string;
  assetCount?: number;
}

// ── API 요청/응답 타입 (백엔드 스키마 매칭) ──

// 백엔드 snake_case → 프론트 camelCase 변환 전 원본 타입
export interface AssetApiResponse {
  id: string;
  group_id: string | null;
  type: AssetType;
  status: AssetStatus;
  name: string;
  ticker: string | null;
  currency: Currency;
  quantity: number;
  purchase_price: number;
  current_price: number | null;
  metadata_json: Record<string, unknown> | null;
  sold_at: string | null;
  sold_price: number | null;
  realized_pnl: number | null;
  source: AssetSource;
  trading_account_id: string | null;
  external_ticker: string | null;
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AssetListApiResponse {
  assets: AssetApiResponse[];
  total: number;
}

// ── Phase 6: 종목별 보유 분해 (전략 N주 + 수동 M주 + KIS 잔고) ──

export interface HoldingBreakdownItemApi {
  account_id: string;
  ticker: string;
  ticker_name: string;
  strategy_qty: string;
  advisory_qty: string;
  kis_qty: string | null;
  mismatch_qty: string;
  has_mismatch: boolean;
}

export interface HoldingBreakdownApiResponse {
  items: HoldingBreakdownItemApi[];
  mismatches: string[];
}

export interface HoldingBreakdownItem {
  accountId: string;
  ticker: string;
  tickerName: string;
  strategyQty: number;
  advisoryQty: number;
  kisQty: number | null;
  mismatchQty: number;
  hasMismatch: boolean;
}

export interface HoldingBreakdown {
  items: HoldingBreakdownItem[];
  mismatches: string[];
}

export function toHoldingBreakdownItem(api: HoldingBreakdownItemApi): HoldingBreakdownItem {
  return {
    accountId: api.account_id,
    ticker: api.ticker,
    tickerName: api.ticker_name,
    strategyQty: Number(api.strategy_qty),
    advisoryQty: Number(api.advisory_qty),
    kisQty: api.kis_qty == null ? null : Number(api.kis_qty),
    mismatchQty: Number(api.mismatch_qty),
    hasMismatch: api.has_mismatch,
  };
}

export function toHoldingBreakdown(api: HoldingBreakdownApiResponse): HoldingBreakdown {
  return {
    items: api.items.map(toHoldingBreakdownItem),
    mismatches: api.mismatches,
  };
}

export interface GroupApiResponse {
  id: string;
  user_id?: string;
  name: string;
  description: string | null;
  sort_order: number;
  created_at: string;
  asset_count: number;
}

export interface GroupListApiResponse {
  groups: GroupApiResponse[];
  total: number;
}

export interface AssetCreateRequest {
  type: AssetType;
  name: string;
  ticker?: string | null;
  currency: Currency;
  quantity: number;
  purchase_price: number;
  current_price?: number | null;
  group_id?: string | null;
  metadata_json?: Record<string, unknown> | null;
}

export interface AssetUpdateRequest {
  type?: AssetType;
  name?: string;
  ticker?: string | null;
  currency?: Currency;
  quantity?: number;
  purchase_price?: number;
  current_price?: number | null;
  group_id?: string | null;
  metadata_json?: Record<string, unknown> | null;
}

export interface SellRequest {
  sold_price: number;
}

// API → 프론트 변환 헬퍼
export function toAsset(api: AssetApiResponse): Asset {
  return {
    id: api.id,
    groupId: api.group_id,
    type: api.type,
    status: api.status,
    name: api.name,
    ticker: api.ticker,
    quantity: api.quantity,
    purchasePrice: api.purchase_price,
    currentPrice: api.current_price,
    currency: api.currency,
    metadata: api.metadata_json ?? {},
    soldAt: api.sold_at,
    soldPrice: api.sold_price,
    realizedPnl: api.realized_pnl,
    source: api.source,
    tradingAccountId: api.trading_account_id,
    externalTicker: api.external_ticker,
    lastSyncedAt: api.last_synced_at,
    createdAt: api.created_at,
    updatedAt: api.updated_at,
  };
}

export function toGroup(api: GroupApiResponse): PortfolioGroup {
  return {
    id: api.id,
    userId: api.user_id,
    name: api.name,
    description: api.description,
    sortOrder: api.sort_order,
    createdAt: api.created_at,
    assetCount: api.asset_count,
  };
}

// 대시보드 요약
export interface DashboardSummary {
  totalValueKrw: number;
  byType: Record<AssetType, { valueKrw: number; ratio: number }>;
  pnl: {
    total: number;
    realized: number;
    unrealized: number;
    totalRatio: number;
  };
  previousDayChange: {
    amount: number;
    ratio: number;
  };
  updatedAt: string;
}

// 데이터 신뢰도 등급
export type DataFreshness = "realtime" | "delayed" | "batch" | "estimated";

export interface PriceData {
  price: number;
  currency: Currency;
  freshness: DataFreshness;
  fetchedAt: string;
  isStale?: boolean;
}

// ── 시세 갱신 API 타입 ──

export interface RefreshDetailApi {
  ticker: string;
  success: boolean;
  price: number | null;
  currency: string | null;
  error: string | null;
}

export interface ExchangeRateApi {
  from_currency: string;
  to_currency: string;
  rate: number;
  fetched_at: string;
  source: string;
}

export interface RefreshResponseApi {
  success_count: number;
  fail_count: number;
  refreshed_at: string;
  details: RefreshDetailApi[];
  exchange_rates: ExchangeRateApi[];
}

export interface ExchangeRate {
  fromCurrency: string;
  toCurrency: string;
  rate: number;
  fetchedAt: string;
  source: string;
}

export interface PriceModeApi {
  current_mode: DataFreshness;
}

// ── 대시보드 API 타입 ──

export interface TypeBreakdownApi {
  value_krw: number;
  ratio: number;
}

export interface PnlSummaryApi {
  total: number;
  realized: number;
  unrealized: number;
  total_ratio: number;
}

export interface DailyChangeApi {
  amount: number;
  ratio: number;
}

export interface DashboardSummaryApi {
  total_value_krw: number;
  by_type: Record<string, TypeBreakdownApi>;
  pnl: PnlSummaryApi;
  previous_day_change: DailyChangeApi;
  updated_at: string;
}

export interface HistoryDataPointApi {
  date: string;
  total_value_krw: number;
  breakdown: Record<string, unknown> | null;
}

export interface DashboardHistoryApi {
  period: string;
  data_points: HistoryDataPointApi[];
  total_count: number;
}

export interface SnapshotResponseApi {
  id: string;
  snapshot_date: string;
  total_value_krw: number;
  breakdown: Record<string, unknown> | null;
  created_at: string;
}

// API → 프론트 변환
const ASSET_TYPES_SET = new Set<string>(ASSET_TYPE_VALUES);

function isAssetType(key: string): key is AssetType {
  return ASSET_TYPES_SET.has(key);
}

const DEFAULT_TYPE_ENTRY = { valueKrw: 0, ratio: 0 } as const;

// ── Phase 3: 종목 분석 Enums ──

export type ValuationSignal = "undervalued" | "fair" | "overvalued";
export type TradingSignalAction = "buy" | "sell" | "hold";
export const MARKETS = ["KRX", "NASDAQ", "NYSE", "CRYPTO"] as const;
export type MarketType = (typeof MARKETS)[number];
export type RiskLevel = "상" | "중" | "하";
export type SimulationType = "dca" | "portfolio" | "scenario";

// ── Phase 3: 기본적 분석 (Fundamental) ──

export interface FundamentalAnalysisApi {
  ticker: string;
  market: string;
  company_name: string | null;
  sector: string | null;
  per: number | null;
  pbr: number | null;
  roe: number | null;
  eps: number | null;
  sector_avg_per: number | null;
  sector_avg_pbr: number | null;
  per_based_fair_value: number | null;
  current_price: number | null;
  price_gap_pct: number | null;
  valuation_signal: ValuationSignal | null;
  data_source: string | null;
  updated_at: string | null;
  disclaimer: string;
}

export interface FundamentalAnalysis {
  ticker: string;
  market: string;
  companyName: string | null;
  sector: string | null;
  per: number | null;
  pbr: number | null;
  roe: number | null;
  eps: number | null;
  sectorAvgPer: number | null;
  sectorAvgPbr: number | null;
  perBasedFairValue: number | null;
  currentPrice: number | null;
  priceGapPct: number | null;
  valuationSignal: ValuationSignal | null;
  dataSource: string | null;
  updatedAt: string | null;
  disclaimer: string;
}

export function toFundamentalAnalysis(api: FundamentalAnalysisApi): FundamentalAnalysis {
  return {
    ticker: api.ticker,
    market: api.market,
    companyName: api.company_name,
    sector: api.sector,
    per: api.per,
    pbr: api.pbr,
    roe: api.roe,
    eps: api.eps,
    sectorAvgPer: api.sector_avg_per,
    sectorAvgPbr: api.sector_avg_pbr,
    perBasedFairValue: api.per_based_fair_value,
    currentPrice: api.current_price,
    priceGapPct: api.price_gap_pct,
    valuationSignal: api.valuation_signal,
    dataSource: api.data_source,
    updatedAt: api.updated_at,
    disclaimer: api.disclaimer,
  };
}

// ── Phase 3: 기술적 분석 (Technical) ──

export interface TechnicalAnalysisApi {
  ticker: string;
  market: string;
  rsi: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_histogram: number | null;
  bollinger_upper: number | null;
  bollinger_middle: number | null;
  bollinger_lower: number | null;
  sma_5: number | null;
  sma_20: number | null;
  sma_60: number | null;
  sma_120: number | null;
  support_level: number | null;
  resistance_level: number | null;
  current_price: number | null;
  data_source: string | null;
  updated_at: string | null;
  disclaimer: string;
}

export interface TechnicalAnalysis {
  ticker: string;
  market: string;
  rsi: number | null;
  macd: number | null;
  macdSignal: number | null;
  macdHistogram: number | null;
  bollingerUpper: number | null;
  bollingerMiddle: number | null;
  bollingerLower: number | null;
  sma5: number | null;
  sma20: number | null;
  sma60: number | null;
  sma120: number | null;
  supportLevel: number | null;
  resistanceLevel: number | null;
  currentPrice: number | null;
  dataSource: string | null;
  updatedAt: string | null;
  disclaimer: string;
}

export function toTechnicalAnalysis(api: TechnicalAnalysisApi): TechnicalAnalysis {
  return {
    ticker: api.ticker,
    market: api.market,
    rsi: api.rsi,
    macd: api.macd,
    macdSignal: api.macd_signal,
    macdHistogram: api.macd_histogram,
    bollingerUpper: api.bollinger_upper,
    bollingerMiddle: api.bollinger_middle,
    bollingerLower: api.bollinger_lower,
    sma5: api.sma_5,
    sma20: api.sma_20,
    sma60: api.sma_60,
    sma120: api.sma_120,
    supportLevel: api.support_level,
    resistanceLevel: api.resistance_level,
    currentPrice: api.current_price,
    dataSource: api.data_source,
    updatedAt: api.updated_at,
    disclaimer: api.disclaimer,
  };
}

// ── Phase 3: 매매 시그널 ──

export interface TradingSignalsApi {
  ticker: string;
  market: string;
  action: TradingSignalAction;
  confidence: number;
  risk_level: RiskLevel;
  reasons: string[];
  fundamental_score: number | null;
  technical_score: number | null;
  current_price: number | null;
  data_source: string | null;
  updated_at: string | null;
  disclaimer: string;
}

export interface TradingSignals {
  ticker: string;
  market: string;
  action: TradingSignalAction;
  confidence: number;
  riskLevel: RiskLevel;
  reasons: string[];
  fundamentalScore: number | null;
  technicalScore: number | null;
  currentPrice: number | null;
  dataSource: string | null;
  updatedAt: string | null;
  disclaimer: string;
}

export function toTradingSignals(api: TradingSignalsApi): TradingSignals {
  return {
    ticker: api.ticker,
    market: api.market,
    action: api.action,
    confidence: api.confidence,
    riskLevel: api.risk_level,
    reasons: api.reasons,
    fundamentalScore: api.fundamental_score,
    technicalScore: api.technical_score,
    currentPrice: api.current_price,
    dataSource: api.data_source,
    updatedAt: api.updated_at,
    disclaimer: api.disclaimer,
  };
}

// ── Phase 3: 관심종목 (Watchlist) ──

export interface WatchlistItemApi {
  id: string;
  ticker: string;
  market: string;
  target_buy_price: number | null;
  target_sell_price: number | null;
  alert_threshold_pct: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface WatchlistItem {
  id: string;
  ticker: string;
  market: string;
  targetBuyPrice: number | null;
  targetSellPrice: number | null;
  alertThresholdPct: number | null;
  notes: string | null;
  createdAt: string;
  updatedAt: string;
}

export function toWatchlistItem(api: WatchlistItemApi): WatchlistItem {
  return {
    id: api.id,
    ticker: api.ticker,
    market: api.market,
    targetBuyPrice: api.target_buy_price,
    targetSellPrice: api.target_sell_price,
    alertThresholdPct: api.alert_threshold_pct,
    notes: api.notes,
    createdAt: api.created_at,
    updatedAt: api.updated_at,
  };
}

// 프론트엔드 camelCase 요청 타입
export interface WatchlistCreateRequest {
  ticker: string;
  market: MarketType;
  targetBuyPrice?: number | null;
  targetSellPrice?: number | null;
  alertThresholdPct?: number | null;
  notes?: string | null;
}

export interface WatchlistUpdateRequest {
  targetBuyPrice?: number | null;
  targetSellPrice?: number | null;
  alertThresholdPct?: number | null;
  notes?: string | null;
}

// 백엔드 snake_case API 타입
export interface WatchlistCreateRequestApi {
  ticker: string;
  market: MarketType;
  target_buy_price?: number | null;
  target_sell_price?: number | null;
  alert_threshold_pct?: number | null;
  notes?: string | null;
}

export interface WatchlistUpdateRequestApi {
  target_buy_price?: number | null;
  target_sell_price?: number | null;
  alert_threshold_pct?: number | null;
  notes?: string | null;
}

export function toWatchlistCreateRequestApi(req: WatchlistCreateRequest): WatchlistCreateRequestApi {
  return {
    ticker: req.ticker,
    market: req.market,
    target_buy_price: req.targetBuyPrice,
    target_sell_price: req.targetSellPrice,
    alert_threshold_pct: req.alertThresholdPct,
    notes: req.notes,
  };
}

export function toWatchlistUpdateRequestApi(req: WatchlistUpdateRequest): WatchlistUpdateRequestApi {
  return {
    target_buy_price: req.targetBuyPrice,
    target_sell_price: req.targetSellPrice,
    alert_threshold_pct: req.alertThresholdPct,
    notes: req.notes,
  };
}

// ── Phase 3: 시뮬레이션 ──

// 프론트엔드 camelCase 타입
export interface DcaSimulationParams {
  type: "dca";
  ticker: string;
  market: MarketType;
  monthlyAmount: number;
  months: number;
}

export interface PortfolioSimulationParams {
  type: "portfolio";
  tickers: string[];
  weights: number[];
  initialAmount: number;
  months: number;
  rebalanceIntervalMonths?: number;
}

export interface ScenarioSimulationParams {
  type: "scenario";
  ticker: string;
  market: MarketType;
  entryPrice: number;
  quantity: number;
  targetPrice: number;
  stopLossPrice: number;
}

export type SimulationParams =
  | DcaSimulationParams
  | PortfolioSimulationParams
  | ScenarioSimulationParams;

// 백엔드 snake_case API 타입
export interface DcaSimulationParamsApi {
  type: "dca";
  ticker: string;
  market: MarketType;
  monthly_amount: number;
  months: number;
}

export interface PortfolioSimulationParamsApi {
  type: "portfolio";
  tickers: string[];
  weights: number[];
  initial_amount: number;
  months: number;
  rebalance_interval_months?: number;
}

export interface ScenarioSimulationParamsApi {
  type: "scenario";
  ticker: string;
  market: MarketType;
  entry_price: number;
  quantity: number;
  target_price: number;
  stop_loss_price: number;
}

export type SimulationParamsApi =
  | DcaSimulationParamsApi
  | PortfolioSimulationParamsApi
  | ScenarioSimulationParamsApi;

export interface SimulationRequestApi {
  params: SimulationParamsApi;
}

export function toSimulationParamsApi(params: SimulationParams): SimulationParamsApi {
  switch (params.type) {
    case "dca":
      return {
        type: "dca",
        ticker: params.ticker,
        market: params.market,
        monthly_amount: params.monthlyAmount,
        months: params.months,
      };
    case "portfolio":
      return {
        type: "portfolio",
        tickers: params.tickers,
        weights: params.weights,
        initial_amount: params.initialAmount,
        months: params.months,
        rebalance_interval_months: params.rebalanceIntervalMonths,
      };
    case "scenario":
      return {
        type: "scenario",
        ticker: params.ticker,
        market: params.market,
        entry_price: params.entryPrice,
        quantity: params.quantity,
        target_price: params.targetPrice,
        stop_loss_price: params.stopLossPrice,
      };
  }
}

function toSimulationParams(api: SimulationParamsApi): SimulationParams {
  switch (api.type) {
    case "dca":
      return {
        type: "dca",
        ticker: api.ticker,
        market: api.market,
        monthlyAmount: api.monthly_amount,
        months: api.months,
      };
    case "portfolio":
      return {
        type: "portfolio",
        tickers: api.tickers,
        weights: api.weights,
        initialAmount: api.initial_amount,
        months: api.months,
        rebalanceIntervalMonths: api.rebalance_interval_months,
      };
    case "scenario":
      return {
        type: "scenario",
        ticker: api.ticker,
        market: api.market,
        entryPrice: api.entry_price,
        quantity: api.quantity,
        targetPrice: api.target_price,
        stopLossPrice: api.stop_loss_price,
      };
  }
}

// Simulation Results (API snake_case)

export interface MonthlyBreakdownItemApi {
  month: number;
  invested: number;
  cumulative_invested: number;
  shares_bought: number;
  cumulative_shares: number;
  price: number;
  portfolio_value: number;
}

export interface DcaSimulationResultApi {
  total_invested: number;
  final_value: number;
  return_rate: number;
  monthly_breakdown: MonthlyBreakdownItemApi[];
}

export interface RebalanceEventApi {
  month: number;
  pre_rebalance_value: number;
  post_rebalance_value: number;
  allocations: Record<string, number>;
}

export interface PortfolioSimulationResultApi {
  total_invested: number;
  final_value: number;
  return_rate: number;
  rebalance_events: RebalanceEventApi[];
}

export interface ScenarioSimulationResultApi {
  potential_profit: number;
  potential_loss: number;
  risk_reward_ratio: number;
  profit_pct: number;
  loss_pct: number;
}

export type SimulationResultApi =
  | DcaSimulationResultApi
  | PortfolioSimulationResultApi
  | ScenarioSimulationResultApi;

export interface SimulationResponseApi {
  id: string;
  type: SimulationType;
  params: SimulationParamsApi;
  result: SimulationResultApi;
  created_at: string;
  expires_at: string;
}

// Simulation Results (camelCase)

export interface MonthlyBreakdownItem {
  month: number;
  invested: number;
  cumulativeInvested: number;
  sharesBought: number;
  cumulativeShares: number;
  price: number;
  portfolioValue: number;
}

export interface DcaSimulationResult {
  totalInvested: number;
  finalValue: number;
  returnRate: number;
  monthlyBreakdown: MonthlyBreakdownItem[];
}

export interface RebalanceEvent {
  month: number;
  preRebalanceValue: number;
  postRebalanceValue: number;
  allocations: Record<string, number>;
}

export interface PortfolioSimulationResult {
  totalInvested: number;
  finalValue: number;
  returnRate: number;
  rebalanceEvents: RebalanceEvent[];
}

export interface ScenarioSimulationResult {
  potentialProfit: number;
  potentialLoss: number;
  riskRewardRatio: number;
  profitPct: number;
  lossPct: number;
}

export type SimulationResult =
  | DcaSimulationResult
  | PortfolioSimulationResult
  | ScenarioSimulationResult;

export interface SimulationResponse {
  id: string;
  type: SimulationType;
  params: SimulationParams;
  result: SimulationResult;
  createdAt: string;
  expiresAt: string;
}

function toDcaResult(api: DcaSimulationResultApi): DcaSimulationResult {
  return {
    totalInvested: api.total_invested,
    finalValue: api.final_value,
    returnRate: api.return_rate,
    monthlyBreakdown: api.monthly_breakdown.map((item) => ({
      month: item.month,
      invested: item.invested,
      cumulativeInvested: item.cumulative_invested,
      sharesBought: item.shares_bought,
      cumulativeShares: item.cumulative_shares,
      price: item.price,
      portfolioValue: item.portfolio_value,
    })),
  };
}

function toPortfolioResult(api: PortfolioSimulationResultApi): PortfolioSimulationResult {
  return {
    totalInvested: api.total_invested,
    finalValue: api.final_value,
    returnRate: api.return_rate,
    rebalanceEvents: api.rebalance_events.map((event) => ({
      month: event.month,
      preRebalanceValue: event.pre_rebalance_value,
      postRebalanceValue: event.post_rebalance_value,
      allocations: event.allocations,
    })),
  };
}

function toScenarioResult(api: ScenarioSimulationResultApi): ScenarioSimulationResult {
  return {
    potentialProfit: api.potential_profit,
    potentialLoss: api.potential_loss,
    riskRewardRatio: api.risk_reward_ratio,
    profitPct: api.profit_pct,
    lossPct: api.loss_pct,
  };
}

export function toSimulationResponse(api: SimulationResponseApi): SimulationResponse {
  let result: SimulationResult;
  if (api.type === "dca") {
    result = toDcaResult(api.result as DcaSimulationResultApi);
  } else if (api.type === "portfolio") {
    result = toPortfolioResult(api.result as PortfolioSimulationResultApi);
  } else {
    result = toScenarioResult(api.result as ScenarioSimulationResultApi);
  }

  return {
    id: api.id,
    type: api.type,
    params: toSimulationParams(api.params),
    result,
    createdAt: api.created_at,
    expiresAt: api.expires_at,
  };
}

// ── 대시보드 변환 ──

export function toDashboardSummary(api: DashboardSummaryApi): DashboardSummary {
  const byType: DashboardSummary["byType"] = Object.fromEntries(
    ASSET_TYPE_VALUES.map((t) => [t, { ...DEFAULT_TYPE_ENTRY }]),
  ) as DashboardSummary["byType"];

  for (const [key, val] of Object.entries(api.by_type)) {
    if (!isAssetType(key)) {
      console.warn(`Unknown asset type from API: ${key}`);
      continue;
    }
    byType[key] = { valueKrw: Number(val.value_krw), ratio: Number(val.ratio) };
  }

  return {
    totalValueKrw: Number(api.total_value_krw),
    byType,
    pnl: {
      total: Number(api.pnl.total),
      realized: Number(api.pnl.realized),
      unrealized: Number(api.pnl.unrealized),
      totalRatio: Number(api.pnl.total_ratio),
    },
    previousDayChange: {
      amount: Number(api.previous_day_change.amount),
      ratio: Number(api.previous_day_change.ratio),
    },
    updatedAt: api.updated_at,
  };
}
