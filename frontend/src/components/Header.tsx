import { useStore } from '../state/store'

function Money({ v, signed = false }: { v: number; signed?: boolean }) {
  const cls = v > 0 ? 'pos' : v < 0 ? 'neg' : 'flat-color'
  const sign = signed && v > 0 ? '+' : ''
  return <span className={signed ? cls : undefined}>{sign}${Math.abs(v) >= 1000 ? v.toLocaleString(undefined, { maximumFractionDigits: 0 }) : v.toFixed(2)}</span>
}

export function Header() {
  const connected = useStore((s) => s.connected)
  const mode = useStore((s) => s.mode)
  const readOnly = useStore((s) => s.readOnly)
  const modeSwitching = useStore((s) => s.modeSwitching)
  const switchMode = useStore((s) => s.switchMode)
  const account = useStore((s) => s.account)
  const risk = useStore((s) => s.risk)
  const rearm = useStore((s) => s.rearm)
  const setHelpOpen = useStore((s) => s.setHelpOpen)

  const dayPnl = (account?.day_realized_pnl ?? 0) + (account?.day_unrealized_pnl ?? 0)
  const lossUsed = risk && risk.daily_max_loss > 0
    ? Math.min(1, Math.max(0, -risk.day_realized_pnl) / risk.daily_max_loss)
    : 0
  const meterClass = lossUsed > 0.75 ? 'danger' : lossUsed > 0.4 ? 'warn' : ''

  return (
    <div className="header">
      <span className="brand">Stock<span>Trade</span></span>
      <div className="mode-switch" title="SIM = synthetic market + paper fills. PAPER = your IBKR paper account (needs TWS/IB Gateway running).">
        {(['sim', 'paper'] as const).map((m) => (
          <button
            key={m}
            className={`mode-btn mode-${m} ${mode === m ? 'active' : ''}`}
            disabled={modeSwitching || mode === m}
            onClick={() => void switchMode(m)}
          >
            {modeSwitching && mode !== m ? '…' : m}
          </button>
        ))}
      </div>
      {readOnly && (
        <span
          className="ro-badge"
          title="Connected to a LIVE IBKR account for market data only. All order paths are disabled until you connect to a paper port (7497/4002)."
        >
          🔒 DATA ONLY — LIVE ACCT
        </span>
      )}
      <span className={`conn-dot ${connected ? 'up' : ''}`} title={connected ? 'Connected' : 'Disconnected'} />

      <div className="stat">
        <span className="label">Equity</span>
        <span className="value">{account ? <Money v={account.equity} /> : '—'}</span>
      </div>
      <div className="stat">
        <span className="label">Cash</span>
        <span className="value">{account ? <Money v={account.cash} /> : '—'}</span>
      </div>
      <div className="stat">
        <span className="label">Day P&L</span>
        <span className="value">{account ? <Money v={dayPnl} signed /> : '—'}</span>
      </div>
      <div className="stat">
        <span className="label">Realized</span>
        <span className="value">{account ? <Money v={account.day_realized_pnl} signed /> : '—'}</span>
      </div>

      <div className="header-right">
        {risk?.halted ? (
          <span
            className="halt-banner"
            onClick={() => void rearm()}
            title={`${risk.halt_reason ?? ''} — click to re-arm`}
          >
            ⛔ HALTED — {risk.halt_reason} (click to re-arm)
          </span>
        ) : (
          <div className={`risk-meter ${meterClass}`} title={`Daily loss used: ${(lossUsed * 100).toFixed(0)}% of $${risk?.daily_max_loss ?? 0}`}>
            <span className="stat">
              <span className="label">
                Loss limit {risk ? `· streak ${risk.consecutive_losers}/${risk.max_consecutive_losers}` : ''}
              </span>
            </span>
            <div className="track">
              <div className="fill" style={{ width: `${lossUsed * 100}%` }} />
            </div>
          </div>
        )}
        <kbd style={{ cursor: 'pointer' }} onClick={() => setHelpOpen(true)}>? hotkeys</kbd>
      </div>
    </div>
  )
}
