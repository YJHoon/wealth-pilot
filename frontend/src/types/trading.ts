// ── Enum 타입 ──

export type TradingMode = "paper" | "live";
export type StrategyType = "ma_crossover" | "mean_reversion" | "custom";
export type OrderSide = "buy" | "sell";
export type OrderType = "market" | "limit";
export type OrderStatus = "pending" | "submitted" | "filled" | "partial" | "cancelled" | "rejected";
export type ScheduleLogStatus = "success" | "skipped" | "error";

// ── API 응답 타입 (snake_case, 백엔드 매칭) ──

export interface TradingAccountApi {
  id: string;
  mode: TradingMode;
  initial_capital: number;
  cash_balance: number | null;
  is_active: boolean;
  allow_netting: boolean;
  token_expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AutoSelectConfigApi {
  enabled: boolean;
  top_n: number;
  market: "KOSPI" | "KOSDAQ" | "ALL";
  min_volume_value: number;
  blacklist: string[];
}

export interface AutoSelectedTickersInfoApi {
  tickers: string[];
  generated_at: string;
  rule_version: string;
  details?: Array<Record<string, unknown>> | null;
}

export interface AutoTickerSelectionHistoryApi {
  id: string;
  generated_at: string;
  rule_version: string;
  triggered_by: string;
  selected_tickers: Array<Record<string, unknown>>;
  excluded_sample: Array<Record<string, unknown>> | null;
  config_snapshot: Record<string, unknown>;
}

export interface AutoTickerPreviewResponseApi {
  rule_version: string;
  selected: Array<Record<string, unknown>>;
  excluded_sample: Array<Record<string, unknown>>;
  config_snapshot: Record<string, unknown>;
  available_cash: number;
  total_eval: number;
  max_position_pct: number;
}

export interface TradingStrategyApi {
  id: string;
  account_id: string;
  name: string;
  strategy_type: StrategyType;
  params_json: Record<string, number>;
  target_tickers: string[];
  interval_minutes: number;
  is_scheduled: boolean;
  market_hours_only: boolean;
  is_active: boolean;
  initial_capital: number;
  realized_pnl: number;
  priority: number;
  auto_select_config: AutoSelectConfigApi;
  auto_selected_tickers: AutoSelectedTickersInfoApi | null;
  created_at: string;
  updated_at: string;
}

export interface TradingOrderApi {
  id: string;
  account_id: string;
  strategy_id: string | null;
  side: OrderSide;
  ticker: string;
  ticker_name: string;
  quantity: number;
  price: number;
  filled_quantity: number | null;
  filled_price: number | null;
  order_type: OrderType;
  status: OrderStatus;
  kis_order_id: string | null;
  reason: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface TradingPositionApi {
  id: string;
  account_id: string;
  ticker: string;
  ticker_name: string;
  quantity: number;
  avg_buy_price: number;
  current_price: number | null;
  unrealized_pnl: number | null;
  created_at: string;
  updated_at: string;
}

export interface TradingPerformanceApi {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  total_realized_pnl: number;
  total_unrealized_pnl: number;
  initial_capital: number;
  current_value: number;
  return_rate: number;
}

export interface ScheduleLogSummaryApi {
  id: string;
  status: ScheduleLogStatus;
  executed_at: string;
  completed_at: string | null;
  tickers_evaluated: number;
  orders_placed: number;
  orders_filled: number;
  skip_reason: string | null;
  error_message: string | null;
}

export interface ScheduleStatusApi {
  is_active: boolean;
  strategy_id: string | null;
  interval_minutes: number | null;
  next_run_at: string | null;
  last_run: ScheduleLogSummaryApi | null;
}

// ── 프론트엔드 타입 (camelCase) ──

export interface TradingAccount {
  id: string;
  mode: TradingMode;
  initialCapital: number;
  cashBalance: number | null;
  isActive: boolean;
  allowNetting: boolean;
  tokenExpiresAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface AutoSelectConfig {
  enabled: boolean;
  topN: number;
  market: "KOSPI" | "KOSDAQ" | "ALL";
  minVolumeValue: number;
  blacklist: string[];
}

export interface AutoSelectedTickersInfo {
  tickers: string[];
  generatedAt: string;
  ruleVersion: string;
  details?: Array<Record<string, unknown>> | null;
}

export interface AutoTickerSelectionHistory {
  id: string;
  generatedAt: string;
  ruleVersion: string;
  triggeredBy: string;
  selectedTickers: Array<Record<string, unknown>>;
  excludedSample: Array<Record<string, unknown>> | null;
  configSnapshot: Record<string, unknown>;
}

export interface AutoTickerPreviewResponse {
  ruleVersion: string;
  selected: Array<Record<string, unknown>>;
  excludedSample: Array<Record<string, unknown>>;
  configSnapshot: Record<string, unknown>;
  availableCash: number;
  totalEval: number;
  maxPositionPct: number;
}

export interface TradingStrategy {
  id: string;
  accountId: string;
  name: string;
  strategyType: StrategyType;
  paramsJson: Record<string, number>;
  targetTickers: string[];
  intervalMinutes: number;
  isScheduled: boolean;
  marketHoursOnly: boolean;
  isActive: boolean;
  initialCapital: number;
  realizedPnl: number;
  priority: number;
  autoSelectConfig: AutoSelectConfig;
  autoSelectedTickers: AutoSelectedTickersInfo | null;
  createdAt: string;
  updatedAt: string;
}

export interface TradingOrder {
  id: string;
  accountId: string;
  strategyId: string | null;
  side: OrderSide;
  ticker: string;
  tickerName: string;
  quantity: number;
  price: number;
  filledQuantity: number | null;
  filledPrice: number | null;
  orderType: OrderType;
  status: OrderStatus;
  kisOrderId: string | null;
  reason: string | null;
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface TradingPosition {
  id: string;
  accountId: string;
  ticker: string;
  tickerName: string;
  quantity: number;
  avgBuyPrice: number;
  currentPrice: number | null;
  unrealizedPnl: number | null;
  createdAt: string;
  updatedAt: string;
}

export interface TradingPerformance {
  totalTrades: number;
  winningTrades: number;
  losingTrades: number;
  winRate: number;
  totalRealizedPnl: number;
  totalUnrealizedPnl: number;
  initialCapital: number;
  currentValue: number;
  returnRate: number;
}

export interface ScheduleStatus {
  isActive: boolean;
  strategyId: string | null;
  intervalMinutes: number | null;
  nextRunAt: string | null;
  lastRun: ScheduleLogSummaryApi | null;
}

// ── KIS 실시간 잔고 타입 ──

export interface KisHolding {
  ticker: string;
  name: string;
  quantity: number;
  avgPrice: number;
  currentPrice: number;
  evalAmount: number;
  pnl: number;
  pnlRate: number;
}

export interface KisBalance {
  cash: number;
  totalEval: number;
  totalPnl: number;
  holdings: KisHolding[];
}

export interface KisBalanceApi {
  cash: number;
  total_eval: number;
  total_pnl: number;
  holdings: {
    ticker: string;
    name: string;
    quantity: number;
    avg_price: number;
    current_price: number;
    eval_amount: number;
    pnl: number;
    pnl_rate: number;
  }[];
}

export function toKisBalance(api: KisBalanceApi): KisBalance {
  return {
    cash: api.cash,
    totalEval: api.total_eval,
    totalPnl: api.total_pnl,
    holdings: api.holdings.map((h) => ({
      ticker: h.ticker,
      name: h.name,
      quantity: h.quantity,
      avgPrice: h.avg_price,
      currentPrice: h.current_price,
      evalAmount: h.eval_amount,
      pnl: h.pnl,
      pnlRate: h.pnl_rate,
    })),
  };
}

// ── 요청 타입 (snake_case, API 직접 전송) ──

export interface TradingAccountCreateRequest {
  mode: TradingMode;
}

export interface TradingAccountUpdateRequest {
  allow_netting?: boolean;
}

export interface AutoSelectConfigRequest {
  enabled: boolean;
  top_n: number;
  market: "KOSPI" | "KOSDAQ" | "ALL";
  min_volume_value: number;
  blacklist: string[];
}

export interface TradingStrategyCreateRequest {
  account_id: string;
  name: string;
  strategy_type: StrategyType;
  params_json: Record<string, number>;
  target_tickers?: string[];
  interval_minutes: number;
  market_hours_only: boolean;
  priority?: number;
  initial_capital: number;
  auto_select_config?: AutoSelectConfigRequest;
}

export interface TradingStrategyUpdateRequest {
  name?: string;
  params_json?: Record<string, number>;
  target_tickers?: string[];
  interval_minutes?: number;
  market_hours_only?: boolean;
  priority?: number;
  initial_capital?: number;
  auto_select_config?: AutoSelectConfigRequest;
}

export interface RebalanceAllocationItem {
  strategy_id: string;
  initial_capital: number;
}

export interface AccountRebalanceRequest {
  allocations: RebalanceAllocationItem[];
}

export interface AccountCapitalSummary {
  accountTotal: number;
  allocated: number;
  available: number;
}

export interface AccountCapitalSummaryApi {
  account_total: number;
  allocated: number;
  available: number;
}

export function toAccountCapitalSummary(
  api: AccountCapitalSummaryApi,
): AccountCapitalSummary {
  return {
    accountTotal: Number(api.account_total),
    allocated: Number(api.allocated),
    available: Number(api.available),
  };
}

export type DepositAllocationMode = "manual" | "pro_rata" | "reserve";

export interface DepositAllocationItem {
  strategy_id: string;
  amount: number;
}

export interface AccountDepositRequest {
  amount: number;
  mode: DepositAllocationMode;
  allocations?: DepositAllocationItem[];
}

// ── 변환 함수 ──

export function toTradingAccount(api: TradingAccountApi): TradingAccount {
  return {
    id: api.id,
    mode: api.mode,
    initialCapital: api.initial_capital,
    cashBalance: api.cash_balance,
    isActive: api.is_active,
    allowNetting: api.allow_netting ?? false,
    tokenExpiresAt: api.token_expires_at,
    createdAt: api.created_at,
    updatedAt: api.updated_at,
  };
}

export function toAutoSelectConfig(api: AutoSelectConfigApi | null | undefined): AutoSelectConfig {
  return {
    enabled: api?.enabled ?? false,
    topN: api?.top_n ?? 10,
    market: api?.market ?? "ALL",
    minVolumeValue: api?.min_volume_value ?? 10_000_000_000,
    blacklist: api?.blacklist ?? [],
  };
}

export function toAutoSelectedTickersInfo(
  api: AutoSelectedTickersInfoApi | null | undefined,
): AutoSelectedTickersInfo | null {
  if (!api) return null;
  return {
    tickers: api.tickers,
    generatedAt: api.generated_at,
    ruleVersion: api.rule_version,
    details: api.details ?? null,
  };
}

export function toAutoTickerHistory(api: AutoTickerSelectionHistoryApi): AutoTickerSelectionHistory {
  return {
    id: api.id,
    generatedAt: api.generated_at,
    ruleVersion: api.rule_version,
    triggeredBy: api.triggered_by,
    selectedTickers: api.selected_tickers ?? [],
    excludedSample: api.excluded_sample ?? null,
    configSnapshot: api.config_snapshot ?? {},
  };
}

export function toAutoTickerPreview(api: AutoTickerPreviewResponseApi): AutoTickerPreviewResponse {
  return {
    ruleVersion: api.rule_version,
    selected: api.selected ?? [],
    excludedSample: api.excluded_sample ?? [],
    configSnapshot: api.config_snapshot ?? {},
    availableCash: api.available_cash,
    totalEval: api.total_eval,
    maxPositionPct: api.max_position_pct,
  };
}

export function toTradingStrategy(api: TradingStrategyApi): TradingStrategy {
  return {
    id: api.id,
    accountId: api.account_id,
    name: api.name,
    strategyType: api.strategy_type,
    paramsJson: api.params_json,
    targetTickers: api.target_tickers,
    intervalMinutes: api.interval_minutes,
    isScheduled: api.is_scheduled,
    marketHoursOnly: api.market_hours_only,
    isActive: api.is_active,
    initialCapital: api.initial_capital ?? 0,
    realizedPnl: api.realized_pnl ?? 0,
    priority: api.priority ?? 0,
    autoSelectConfig: toAutoSelectConfig(api.auto_select_config),
    autoSelectedTickers: toAutoSelectedTickersInfo(api.auto_selected_tickers),
    createdAt: api.created_at,
    updatedAt: api.updated_at,
  };
}

export function toTradingOrder(api: TradingOrderApi): TradingOrder {
  return {
    id: api.id,
    accountId: api.account_id,
    strategyId: api.strategy_id,
    side: api.side,
    ticker: api.ticker,
    tickerName: api.ticker_name,
    quantity: api.quantity,
    price: api.price,
    filledQuantity: api.filled_quantity,
    filledPrice: api.filled_price,
    orderType: api.order_type,
    status: api.status,
    kisOrderId: api.kis_order_id,
    reason: api.reason,
    errorMessage: api.error_message,
    createdAt: api.created_at,
    updatedAt: api.updated_at,
  };
}

export function toTradingPosition(api: TradingPositionApi): TradingPosition {
  return {
    id: api.id,
    accountId: api.account_id,
    ticker: api.ticker,
    tickerName: api.ticker_name,
    quantity: api.quantity,
    avgBuyPrice: api.avg_buy_price,
    currentPrice: api.current_price,
    unrealizedPnl: api.unrealized_pnl,
    createdAt: api.created_at,
    updatedAt: api.updated_at,
  };
}

export function toTradingPerformance(api: TradingPerformanceApi): TradingPerformance {
  return {
    totalTrades: api.total_trades,
    winningTrades: api.winning_trades,
    losingTrades: api.losing_trades,
    winRate: api.win_rate,
    totalRealizedPnl: api.total_realized_pnl,
    totalUnrealizedPnl: api.total_unrealized_pnl,
    initialCapital: api.initial_capital,
    currentValue: api.current_value,
    returnRate: api.return_rate,
  };
}

export function toScheduleStatus(api: ScheduleStatusApi): ScheduleStatus {
  return {
    isActive: api.is_active,
    strategyId: api.strategy_id,
    intervalMinutes: api.interval_minutes,
    nextRunAt: api.next_run_at,
    lastRun: api.last_run,
  };
}

// ── 라벨맵 ──

export const tradingModeLabels: Record<TradingMode, string> = {
  paper: "모의투자",
  live: "실전",
};

export const strategyTypeLabels: Record<StrategyType, string> = {
  ma_crossover: "이동평균 교차",
  mean_reversion: "평균회귀",
  custom: "커스텀",
};

export const orderSideLabels: Record<OrderSide, string> = {
  buy: "매수",
  sell: "매도",
};

export const orderStatusLabels: Record<OrderStatus, string> = {
  pending: "대기",
  submitted: "접수",
  filled: "체결",
  partial: "부분체결",
  cancelled: "취소",
  rejected: "거부",
};
