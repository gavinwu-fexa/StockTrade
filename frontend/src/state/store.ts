import { create } from 'zustand'
import { api, connectWs } from '../api/client'
import type {
  Account, Bar, BacktestResult, FillEvent, PickerInfo, Position, Quote,
  RiskState, ScannerResult, Signal, StagedOrder, StrategyInfo, Toast,
} from '../types'

let toastId = 0

// Insert or replace a bar keeping the list ascending by timestamp —
// the chart library hard-asserts on ordering.
function upsertBar(bars: Bar[], bar: Bar): Bar[] {
  const out = [...bars]
  let i = out.length - 1
  while (i >= 0 && out[i].ts > bar.ts) i--
  if (i >= 0 && out[i].ts === bar.ts) out[i] = bar
  else out.splice(i + 1, 0, bar)
  return out.length > 600 ? out.slice(-600) : out
}

interface AppState {
  connected: boolean
  mode: string
  readOnly: boolean
  marketCondition: string
  account: Account | null
  risk: RiskState | null
  scanner: ScannerResult[]
  selected: string | null
  bars: Bar[]
  quote: Quote | null
  positions: Position[]
  fills: FillEvent[]
  signals: Signal[]
  strategies: StrategyInfo[]
  pickers: PickerInfo[]
  activeStrategy: string
  activePicker: string
  strategyParams: Record<string, unknown>
  shareSize: number
  autoTrade: boolean
  staged: StagedOrder | null
  toasts: Toast[]
  helpOpen: boolean
  backtest: BacktestResult | null
  backtestRunning: boolean
  panicArmedAt: number | null

  init: () => void
  selectSymbol: (symbol: string) => Promise<void>
  cycleSymbol: (dir: 1 | -1) => void
  toast: (kind: Toast['kind'], text: string) => void
  dismissToast: (id: number) => void
  setShareSize: (n: number) => void
  setAutoTrade: (on: boolean) => void
  setStrategy: (name: string, params?: Record<string, unknown>) => Promise<void>
  setStrategyParams: (params: Record<string, unknown>) => Promise<void>
  setMarketCondition: (c: string) => Promise<void>
  switchMode: (mode: string) => Promise<void>
  modeSwitching: boolean
  buyMarket: () => Promise<void>
  sellHalf: () => Promise<void>
  flattenSelected: () => Promise<void>
  flattenAll: () => Promise<void>
  cancelAll: () => Promise<void>
  rearm: () => Promise<void>
  stageOrder: (side: 'buy' | 'sell') => void
  nudgeStaged: (cents: number) => void
  sendStaged: () => Promise<void>
  clearStaged: () => void
  sizePreset: (fraction: number) => void
  setHelpOpen: (open: boolean) => void
  runBacktest: (req: {
    strategy: string
    params?: Record<string, unknown>
    data_source?: string
    symbol?: string
    days?: number
    seed?: number
  }) => Promise<void>
}

export const useStore = create<AppState>((set, get) => ({
  connected: false,
  mode: 'sim',
  readOnly: false,
  marketCondition: 'hot',
  account: null,
  risk: null,
  scanner: [],
  selected: null,
  bars: [],
  quote: null,
  positions: [],
  fills: [],
  signals: [],
  strategies: [],
  pickers: [],
  activeStrategy: 'macd_cross',
  activePicker: 'ross_cameron',
  strategyParams: {},
  shareSize: 100,
  autoTrade: false,
  staged: null,
  toasts: [],
  helpOpen: false,
  backtest: null,
  backtestRunning: false,
  panicArmedAt: null,
  modeSwitching: false,

  init: () => {
    api.state().then(async (s) => {
      set({
        mode: s.mode,
        readOnly: Boolean(s.read_only),
        marketCondition: s.market_condition,
        shareSize: s.share_size,
        autoTrade: s.auto_trade,
        strategies: s.strategies,
        pickers: s.pickers,
        activeStrategy: s.active_strategy,
        activePicker: s.active_picker,
        strategyParams: s.strategy_params,
        risk: s.risk,
      })
      if (s.selected_symbol) {
        set({ selected: s.selected_symbol })
        const bars = await api.bars(s.selected_symbol)
        set({ bars })
      }
    }).catch(() => get().toast('error', 'Backend unreachable — start it with: make backend'))

    connectWs((type, data) => {
      const st = get()
      switch (type) {
        case 'scanner':
          set({ scanner: data })
          break
        case 'quote':
          if (data.symbol === st.selected) set({ quote: data })
          break
        case 'bar':
        case 'bar_update':
          if (data.symbol === st.selected) {
            set({ bars: upsertBar(st.bars, data) })
          }
          break
        case 'account':
          set({ account: data })
          break
        case 'positions':
          set({ positions: data })
          break
        case 'risk':
          set({ risk: data })
          break
        case 'fill':
          set({ fills: [data, ...st.fills].slice(0, 200) })
          st.toast(
            data.side === 'buy' ? 'success' : 'info',
            `${data.side.toUpperCase()} ${data.qty} ${data.symbol} @ $${data.price.toFixed(2)}`,
          )
          break
        case 'signal':
          set({ signals: [data, ...st.signals].slice(0, 200) })
          break
        case 'trade_closed': {
          const pnl = data.pnl as number
          st.toast(pnl >= 0 ? 'success' : 'warn',
            `Closed ${data.symbol}: ${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`)
          break
        }
        case 'order_rejected':
          st.toast('error', `Rejected ${data.side} ${data.symbol}: ${data.reason}`)
          break
        case 'selected':
          if (data.symbol && data.symbol !== st.selected) {
            set({ selected: data.symbol, bars: [], quote: null })
            api.bars(data.symbol).then((bars) => set({ bars }))
          }
          break
        case 'mode': {
          const readOnly = Boolean(data.read_only)
          if (data.mode !== st.mode || readOnly !== st.readOnly) {
            set({
              mode: data.mode, readOnly,
              scanner: [], signals: [], fills: [], positions: [],
            })
            st.toast(
              readOnly ? 'warn' : 'info',
              readOnly
                ? `Mode: ${String(data.mode).toUpperCase()} — LIVE account on port ${data.port}: READ-ONLY, orders disabled`
                : `Mode: ${String(data.mode).toUpperCase()}`,
            )
          }
          break
        }
      }
    }, (up) => set({ connected: up }))
  },

  selectSymbol: async (symbol: string) => {
    set({ selected: symbol, bars: [], quote: null, staged: null })
    const [bars] = await Promise.all([api.bars(symbol), api.select(symbol)])
    set({ bars })
  },

  cycleSymbol: (dir) => {
    const { scanner, selected, selectSymbol } = get()
    if (!scanner.length) return
    const idx = scanner.findIndex((r) => r.symbol === selected)
    const next = scanner[(idx + dir + scanner.length) % scanner.length]
    void selectSymbol(next.symbol)
  },

  toast: (kind, text) => {
    if (get().toasts.some((t) => t.text === text)) return  // dedupe repeats
    const id = ++toastId
    set((s) => ({ toasts: [...s.toasts, { id, kind, text }] }))
    setTimeout(() => get().dismissToast(id), 4000)
  },

  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

  setShareSize: (n) => {
    n = Math.max(1, Math.round(n))
    set({ shareSize: n })
    void api.updateSettings({ share_size: n })
  },

  setAutoTrade: (on) => {
    set({ autoTrade: on })
    void api.updateSettings({ auto_trade: on })
    get().toast('info', on ? 'Auto-trade ON — strategy signals will execute' : 'Auto-trade off')
  },

  setStrategy: async (name, params) => {
    const s = await api.updateSettings({ active_strategy: name, strategy_params: params })
    set({ activeStrategy: s.active_strategy, strategyParams: s.strategy_params })
    get().toast('info', `Strategy: ${name}`)
  },

  setStrategyParams: async (params) => {
    const s = await api.updateSettings({ strategy_params: params })
    set({ strategyParams: s.strategy_params })
    get().toast('success', 'Strategy parameters applied')
  },

  switchMode: async (mode) => {
    set({ modeSwitching: true })
    try {
      await api.setMode(mode)
      // 'mode' + 'selected' WS events finish the transition
    } catch (e) {
      const msg = String(e).replace(/^Error:\s*\/mode:\s*\d+\s*/, '')
      let detail = msg
      try { detail = JSON.parse(msg).detail ?? msg } catch { /* raw text */ }
      get().toast('error', detail)
    } finally {
      set({ modeSwitching: false })
    }
  },

  setMarketCondition: async (c) => {
    await api.updateSettings({ market_condition: c })
    set({ marketCondition: c })
  },

  buyMarket: async () => {
    const { selected, shareSize, toast } = get()
    if (!selected) return toast('warn', 'No symbol selected')
    try {
      const res = await api.placeOrder({ symbol: selected, side: 'buy', qty: shareSize })
      if (!res.ok) toast('error', res.error ?? 'Order failed')
      else res.warnings?.forEach((w: string) => toast('warn', w))
    } catch (e) {
      toast('error', String(e))
    }
  },

  sellHalf: async () => {
    const { selected, positions, toast } = get()
    if (!selected) return
    const pos = positions.find((p) => p.symbol === selected)
    if (!pos || pos.qty <= 0) return toast('warn', `No position in ${selected}`)
    const qty = Math.max(1, Math.floor(pos.qty / 2))
    const res = await api.placeOrder({ symbol: selected, side: 'sell', qty })
    if (!res.ok) toast('error', res.error ?? 'Order failed')
  },

  flattenSelected: async () => {
    const { selected, toast } = get()
    if (!selected) return
    await api.flatten(selected)
    toast('info', `Flattened ${selected}`)
  },

  flattenAll: async () => {
    await api.cancelAll()
    await api.flatten(null)
    get().toast('warn', 'FLATTENED ALL positions + cancelled all orders')
  },

  cancelAll: async () => {
    const res = await api.cancelAll()
    get().toast('info', `Cancelled ${res.cancelled} order(s)`)
  },

  rearm: async () => {
    const risk = await api.rearm()
    set({ risk })
    get().toast('info', 'Risk halt cleared — trading re-armed')
  },

  stageOrder: (side) => {
    const { selected, quote, shareSize, positions } = get()
    if (!selected || !quote) return
    const qty = side === 'sell'
      ? (positions.find((p) => p.symbol === selected)?.qty ?? shareSize)
      : shareSize
    set({
      staged: {
        side,
        symbol: selected,
        qty,
        limitPrice: side === 'buy' ? quote.ask : quote.bid,
      },
    })
  },

  nudgeStaged: (cents) => {
    const { staged } = get()
    if (!staged) return
    set({
      staged: {
        ...staged,
        limitPrice: Math.max(0.01, Math.round((staged.limitPrice + cents / 100) * 100) / 100),
      },
    })
  },

  sendStaged: async () => {
    const { staged, toast } = get()
    if (!staged) return
    set({ staged: null })
    const res = await api.placeOrder({
      symbol: staged.symbol,
      side: staged.side,
      qty: staged.qty,
      type: 'limit',
      limit_price: staged.limitPrice,
    })
    if (!res.ok) toast('error', res.error ?? 'Order failed')
    else toast('info', `Limit ${staged.side} ${staged.qty} ${staged.symbol} @ $${staged.limitPrice.toFixed(2)} working`)
  },

  clearStaged: () => set({ staged: null }),

  sizePreset: (fraction) => {
    const { account, quote, setShareSize, toast } = get()
    if (!account || !quote || quote.ask <= 0) return
    const qty = Math.floor((account.cash * fraction) / quote.ask)
    if (qty < 1) return toast('warn', 'Not enough buying power for that size')
    setShareSize(qty)
    toast('info', `Share size: ${qty} (${Math.round(fraction * 100)}% of cash)`)
  },

  setHelpOpen: (open) => set({ helpOpen: open }),

  runBacktest: async (req) => {
    set({ backtestRunning: true })
    try {
      const result = await api.backtest(req)
      set({ backtest: result })
    } catch (e) {
      const msg = String(e)
      let detail = msg
      const jsonStart = msg.indexOf('{')
      if (jsonStart >= 0) {
        try { detail = JSON.parse(msg.slice(jsonStart)).detail ?? msg } catch { /* raw */ }
      }
      get().toast('error', `Backtest failed: ${detail}`)
    } finally {
      set({ backtestRunning: false })
    }
  },
}))
