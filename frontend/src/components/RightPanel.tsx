import { useState } from 'react'
import { useStore } from '../state/store'
import { BacktestTab } from './BacktestTab'
import { HistoryTab } from './HistoryTab'
import { OrderPanel } from './OrderPanel'

function fmtTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function PositionsTab() {
  const positions = useStore((s) => s.positions)
  const selectSymbol = useStore((s) => s.selectSymbol)
  if (!positions.length) return <div className="empty-note">No open positions</div>
  return (
    <table className="data-table">
      <thead>
        <tr><th>Sym</th><th>Qty</th><th>Avg</th><th>Last</th><th>P&L</th></tr>
      </thead>
      <tbody>
        {positions.map((p) => (
          <tr key={p.symbol} onClick={() => void selectSymbol(p.symbol)} style={{ cursor: 'pointer' }}>
            <td>{p.symbol}</td>
            <td>{p.qty}</td>
            <td>{p.avg_price.toFixed(2)}</td>
            <td>{p.last_price.toFixed(2)}</td>
            <td className={p.unrealized_pnl >= 0 ? 'pos' : 'neg'}>
              {p.unrealized_pnl >= 0 ? '+' : ''}{p.unrealized_pnl.toFixed(2)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function FillsTab() {
  const fills = useStore((s) => s.fills)
  if (!fills.length) return <div className="empty-note">No fills yet — press ⇧B to buy</div>
  return (
    <div>
      {fills.map((f, i) => (
        <div className="log-row" key={i}>
          <span className="time">{fmtTime(f.ts)}</span>
          <span className={`badge ${f.side}`}>{f.side}</span>
          <span className="body"><b>{f.qty} {f.symbol}</b> @ ${f.price.toFixed(2)}</span>
        </div>
      ))}
    </div>
  )
}

function SignalsTab() {
  const signals = useStore((s) => s.signals)
  const autoTrade = useStore((s) => s.autoTrade)
  if (!signals.length) {
    return (
      <div className="empty-note">
        No strategy signals yet{autoTrade ? '' : ' (auto-trade is off — signals are advisory)'}
      </div>
    )
  }
  return (
    <div>
      {signals.map((sig, i) => (
        <div className="log-row" key={i}>
          <span className="time">{fmtTime(sig.ts)}</span>
          <span className={`badge ${sig.type === 'enter_long' ? 'enter' : 'exit'}`}>
            {sig.type === 'enter_long' ? 'entry' : 'exit'}
          </span>
          <span className="body">
            <b>{sig.symbol}</b> @ ${sig.price.toFixed(2)} — {sig.reason}
          </span>
        </div>
      ))}
    </div>
  )
}

export function RightPanel() {
  const [tab, setTab] = useState<'positions' | 'fills' | 'signals' | 'backtest' | 'history'>('positions')
  const positions = useStore((s) => s.positions)
  const fills = useStore((s) => s.fills)
  const signals = useStore((s) => s.signals)

  return (
    <div className="panel right-col">
      <OrderPanel />
      <div className="tabs">
        {([
          ['positions', `Pos`, positions.length],
          ['fills', 'Fills', fills.length],
          ['signals', 'Signals', signals.length],
          ['backtest', 'Backtest', 0],
          ['history', 'History', 0],
        ] as const).map(([key, label, count]) => (
          <div
            key={key}
            className={`tab ${tab === key ? 'active' : ''}`}
            onClick={() => setTab(key)}
          >
            {label}
            {count > 0 && <span className="count">{count}</span>}
          </div>
        ))}
      </div>
      <div className="tab-body">
        {tab === 'positions' && <PositionsTab />}
        {tab === 'fills' && <FillsTab />}
        {tab === 'signals' && <SignalsTab />}
        {tab === 'backtest' && <BacktestTab />}
        {tab === 'history' && <HistoryTab />}
      </div>
    </div>
  )
}
