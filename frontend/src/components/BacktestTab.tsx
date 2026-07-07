import { useState } from 'react'
import { useStore } from '../state/store'
import { ParamsEditor } from './ParamsEditor'

function EquitySpark({ curve }: { curve: { ts: number; equity: number }[] }) {
  if (curve.length < 2) return null
  const w = 280
  const h = 60
  const values = curve.map((p) => p.equity)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const pts = curve.map((p, i) => {
    const x = (i / (curve.length - 1)) * w
    const y = h - ((p.equity - min) / span) * (h - 6) - 3
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  const up = values[values.length - 1] >= values[0]
  return (
    <div className="equity-spark">
      <svg width={w} height={h} style={{ display: 'block' }}>
        <polyline
          points={pts.join(' ')}
          fill="none"
          stroke={up ? '#00e676' : '#ff5252'}
          strokeWidth="1.5"
        />
      </svg>
    </div>
  )
}

export function BacktestTab() {
  const strategies = useStore((s) => s.strategies)
  const activeStrategy = useStore((s) => s.activeStrategy)
  const backtest = useStore((s) => s.backtest)
  const running = useStore((s) => s.backtestRunning)
  const runBacktest = useStore((s) => s.runBacktest)

  const [strategy, setStrategy] = useState(activeStrategy)
  const [days, setDays] = useState(5)
  const [seed, setSeed] = useState(1)
  const [dataSource, setDataSource] = useState<'synthetic' | 'ibkr'>('synthetic')
  const [symbol, setSymbol] = useState('AAPL')
  const [params, setParams] = useState<Record<string, unknown> | undefined>(undefined)
  const [showParams, setShowParams] = useState(false)

  const strategyInfo = strategies.find((st) => st.name === strategy)
  const effectiveParams = params ?? (strategyInfo?.default_params as Record<string, unknown>) ?? {}
  const m = backtest?.metrics

  return (
    <div>
      <div className="backtest-form">
        <div className="row">
          <span>Strategy</span>
          <select
            value={strategy}
            onChange={(e) => { setStrategy(e.target.value); setParams(undefined) }}
          >
            {strategies.map((st) => (
              <option key={st.name} value={st.name}>{st.label}</option>
            ))}
          </select>
        </div>
        <div className="row">
          <span>Data</span>
          <select value={dataSource} onChange={(e) => setDataSource(e.target.value as 'synthetic' | 'ibkr')}>
            <option value="synthetic">Synthetic momentum days</option>
            <option value="ibkr">IBKR history (real bars)</option>
          </select>
        </div>
        {dataSource === 'ibkr' ? (
          <div className="row">
            <span>Symbol</span>
            <input
              type="text"
              className="symbol-input"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            />
          </div>
        ) : (
          <div className="row">
            <span>Random seed</span>
            <input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} />
          </div>
        )}
        <div className="row">
          <span>Days of data</span>
          <input type="number" value={days} min={1} max={30} onChange={(e) => setDays(Number(e.target.value))} />
        </div>
        <div className="row">
          <span className="param-toggle" onClick={() => setShowParams(!showParams)}>
            {showParams ? '▾ strategy params' : '▸ strategy params'}
          </span>
        </div>
        {showParams && (
          <ParamsEditor params={effectiveParams} onApply={setParams} applyLabel="Set for next run" />
        )}
        <button
          className="btn-run"
          disabled={running}
          onClick={() => void runBacktest({
            strategy, days, seed, params,
            data_source: dataSource,
            symbol: dataSource === 'ibkr' ? symbol : 'SIM',
          })}
        >
          {running ? 'Running…' : 'Run Backtest'}
        </button>
      </div>

      {m && (
        <>
          <div className="metrics-grid">
            <div className="metric">
              <div className="label">Trades</div>
              <div className="value">{m.trades}</div>
            </div>
            <div className="metric">
              <div className="label">Win rate</div>
              <div className="value">{m.win_rate}%</div>
            </div>
            <div className="metric">
              <div className="label">P/L ratio</div>
              <div className="value">{m.pl_ratio}</div>
            </div>
            <div className="metric">
              <div className="label">Total P&L</div>
              <div className={`value ${m.total_pnl >= 0 ? 'pos' : 'neg'}`}>
                {m.total_pnl >= 0 ? '+' : ''}${m.total_pnl.toFixed(0)}
              </div>
            </div>
            <div className="metric">
              <div className="label">Return</div>
              <div className={`value ${m.return_pct >= 0 ? 'pos' : 'neg'}`}>{m.return_pct}%</div>
            </div>
            <div className="metric">
              <div className="label">Max DD</div>
              <div className="value neg">{m.max_drawdown_pct}%</div>
            </div>
            <div className="metric">
              <div className="label">Avg win</div>
              <div className="value pos">${m.avg_win.toFixed(0)}</div>
            </div>
            <div className="metric">
              <div className="label">Avg loss</div>
              <div className="value neg">${m.avg_loss.toFixed(0)}</div>
            </div>
            <div className="metric">
              <div className="label">Expectancy</div>
              <div className={`value ${m.expectancy >= 0 ? 'pos' : 'neg'}`}>
                ${m.expectancy.toFixed(0)}
              </div>
            </div>
          </div>
          <EquitySpark curve={m.equity_curve} />
          {backtest && backtest.trades.length > 0 && (
            <table className="data-table">
              <thead>
                <tr><th>Exit reason</th><th>Qty</th><th>P&L</th></tr>
              </thead>
              <tbody>
                {backtest.trades.slice(-30).map((t, i) => (
                  <tr key={i}>
                    <td style={{ maxWidth: 170, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={t.exit_reason}>
                      {t.exit_reason}
                    </td>
                    <td>{t.qty}</td>
                    <td className={t.pnl >= 0 ? 'pos' : 'neg'}>
                      {t.pnl >= 0 ? '+' : ''}{t.pnl.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
      {!m && !running && (
        <div className="empty-note">
          Run any registered strategy against synthetic momentum days.
          Same engine, risk rules, and fills as live trading.
        </div>
      )}
    </div>
  )
}
