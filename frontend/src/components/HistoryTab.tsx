import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useStore } from '../state/store'

interface DaySummary {
  day: string
  mode: string
  trades: number
  pnl: number
  wins: number
}

interface TradeRow {
  symbol: string
  exit_ts: number
  qty: number
  pnl: number
  entry_price: number
  exit_price: number
  exit_reason: string
  mode: string
}

export function HistoryTab() {
  const [days, setDays] = useState<DaySummary[]>([])
  const [trades, setTrades] = useState<TradeRow[]>([])
  const [selectedDay, setSelectedDay] = useState<string | null>(null)
  const fills = useStore((s) => s.fills)   // refresh when new fills land

  useEffect(() => {
    api.dailyHistory().then(setDays).catch(() => setDays([]))
  }, [fills.length])

  useEffect(() => {
    api.tradeHistory(selectedDay ?? undefined).then(setTrades).catch(() => setTrades([]))
  }, [selectedDay, fills.length])

  if (!days.length && !trades.length) {
    return <div className="empty-note">No completed trades yet — history persists across restarts</div>
  }

  return (
    <div>
      {days.length > 0 && (
        <table className="data-table">
          <thead>
            <tr><th>Day</th><th>Mode</th><th>Trades</th><th>Win%</th><th>P&L</th></tr>
          </thead>
          <tbody>
            {days.map((d) => (
              <tr
                key={`${d.day}-${d.mode}`}
                onClick={() => setSelectedDay(selectedDay === d.day ? null : d.day)}
                style={{ cursor: 'pointer', background: selectedDay === d.day ? 'var(--bg-elevated)' : undefined }}
              >
                <td>{d.day}</td>
                <td>{d.mode}</td>
                <td>{d.trades}</td>
                <td>{d.trades ? Math.round((d.wins / d.trades) * 100) : 0}%</td>
                <td className={d.pnl >= 0 ? 'pos' : 'neg'}>
                  {d.pnl >= 0 ? '+' : ''}{d.pnl.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="panel-title">{selectedDay ? `Trades — ${selectedDay}` : 'Recent trades'}</div>
      <table className="data-table">
        <thead>
          <tr><th>Sym</th><th>Qty</th><th>In</th><th>Out</th><th>P&L</th></tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr key={i} title={t.exit_reason}>
              <td>{t.symbol}</td>
              <td>{t.qty}</td>
              <td>{t.entry_price.toFixed(2)}</td>
              <td>{t.exit_price.toFixed(2)}</td>
              <td className={t.pnl >= 0 ? 'pos' : 'neg'}>
                {t.pnl >= 0 ? '+' : ''}{t.pnl.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
