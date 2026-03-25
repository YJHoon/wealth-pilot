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
  account_number_masked: string;
  initial_capital: number;
  is_active: boolean;
  token_expires_at: string | null;
  created_at: string;
  updated_at: string;
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
  accountNumberMasked: string;
  initialCapital: number;
  isActive: boolean;
  tokenExpiresAt: string | null;
  createdAt: string;
  updatedAt: string;
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

// ── 요청 타입 (snake_case, API 직접 전송) ──

export interface TradingAccountCreateRequest {
  mode: TradingMode;
  app_key: string;
  app_secret: string;
  account_number: string;
  account_product_code: string;
  initial_capital: number;
}

export interface TradingStrategyCreateRequest {
  account_id: string;
  name: string;
  strategy_type: StrategyType;
  params_json: Record<string, number>;
  target_tickers: string[];
  interval_minutes: number;
  market_hours_only: boolean;
}

export interface TradingStrategyUpdateRequest {
  name?: string;
  params_json?: Record<string, number>;
  target_tickers?: string[];
  interval_minutes?: number;
  market_hours_only?: boolean;
}

// ── 변환 함수 ──

export function toTradingAccount(api: TradingAccountApi): TradingAccount {
  return {
    id: api.id,
    mode: api.mode,
    accountNumberMasked: api.account_number_masked,
    initialCapital: api.initial_capital,
    isActive: api.is_active,
    tokenExpiresAt: api.token_expires_at,
    createdAt: api.created_at,
    updatedAt: api.updated_at,
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
