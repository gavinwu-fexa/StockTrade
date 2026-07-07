import type { BacktestResult } from '../types'

const BASE = '/api'

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${path}: ${res.status} ${await res.text()}`)
  return res.json()
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${path}: ${res.status}`)
  return res.json()
}

export const api = {
  state: () => get<any>('/state'),
  bars: (symbol: string) => get<any[]>(`/bars/${symbol}`),
  scanner: () => get<any[]>('/scanner'),
  select: (symbol: string) => post<any>(`/select/${symbol}`),
  placeOrder: (order: {
    symbol: string
    side: 'buy' | 'sell'
    qty?: number | null
    type?: 'market' | 'limit'
    limit_price?: number | null
    stop_price?: number | null
  }) => post<any>('/orders', order),
  flatten: (symbol?: string | null) => post<any>('/flatten', { symbol: symbol ?? null }),
  cancelAll: () => post<any>('/cancel_all'),
  rearm: () => post<any>('/risk/rearm'),
  updateSettings: (update: Record<string, unknown>) => post<any>('/settings', update),
  backtest: (req: {
    strategy: string
    params?: Record<string, unknown>
    data_source?: string
    symbol?: string
    days?: number
    seed?: number
  }) => post<BacktestResult>('/backtest', req),
  setMode: (mode: string) => post<{ mode: string }>('/mode', { mode }),
  dailyHistory: () => get<any[]>('/history/daily'),
  tradeHistory: (day?: string) => get<any[]>(`/trades${day ? `?day=${day}` : ''}`),
}

export type WsHandler = (type: string, data: any) => void

export function connectWs(onMessage: WsHandler, onStatus: (up: boolean) => void): () => void {
  let ws: WebSocket | null = null
  let closed = false
  let retry = 500

  const open = () => {
    if (closed) return
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${location.host}/ws`)
    ws.onopen = () => {
      retry = 500
      onStatus(true)
    }
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        onMessage(msg.type, msg.data)
      } catch {
        /* ignore malformed frames */
      }
    }
    ws.onclose = () => {
      onStatus(false)
      if (!closed) {
        setTimeout(open, retry)
        retry = Math.min(retry * 2, 5000)
      }
    }
    ws.onerror = () => ws?.close()
  }

  open()
  return () => {
    closed = true
    ws?.close()
  }
}
