export interface Bar {
  symbol: string
  ts: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  timeframe: string
}

export interface Quote {
  symbol: string
  ts: number
  bid: number
  ask: number
  last: number
  bid_size: number
  ask_size: number
}

export interface CriterionCheck {
  name: string
  passed: boolean
  value: string
  detail: string
}

export interface ScannerResult {
  symbol: string
  picker: string
  grade: 'A' | 'B' | 'C'
  score: number
  price: number
  change_pct: number
  relative_volume: number
  float_shares: number | null
  headline: string | null
  checks: CriterionCheck[]
  ts: number
}

export interface Position {
  symbol: string
  qty: number
  avg_price: number
  realized_pnl: number
  last_price: number
  unrealized_pnl: number
  market_value: number
}

export interface Account {
  equity: number
  cash: number
  day_realized_pnl: number
  day_unrealized_pnl: number
  consecutive_losers: number
  trading_halted: boolean
  halt_reason: string | null
}

export interface RiskState {
  day_realized_pnl: number
  daily_max_loss: number
  consecutive_losers: number
  max_consecutive_losers: number
  halted: boolean
  halt_reason: string | null
}

export interface Signal {
  type: 'enter_long' | 'exit_long' | 'scale_out'
  symbol: string
  ts: number
  price: number
  reason: string
  strategy: string
  stop_price: number | null
  target_price: number | null
}

export interface FillEvent {
  kind: string
  ts: number
  symbol: string
  side: 'buy' | 'sell'
  qty: number
  price: number
}

export interface StrategyInfo {
  name: string
  label: string
  description: string
  default_params: Record<string, unknown>
}

export interface PickerInfo {
  name: string
  label: string
  description: string
}

export interface TradeRecord {
  symbol: string
  entry_ts: number
  exit_ts: number
  entry_price: number
  exit_price: number
  qty: number
  pnl: number
  entry_reason: string
  exit_reason: string
}

export interface BacktestMetrics {
  trades: number
  win_rate: number
  avg_win: number
  avg_loss: number
  pl_ratio: number
  expectancy: number
  total_pnl: number
  max_drawdown: number
  max_drawdown_pct: number
  return_pct: number
  max_consecutive_losses: number
  ending_equity: number
  equity_curve: { ts: number; equity: number }[]
}

export interface BacktestResult {
  strategy: string
  params: Record<string, unknown>
  metrics: BacktestMetrics
  trades: TradeRecord[]
}

export interface StagedOrder {
  side: 'buy' | 'sell'
  symbol: string
  qty: number
  limitPrice: number
}

export interface Toast {
  id: number
  kind: 'info' | 'success' | 'error' | 'warn'
  text: string
}
