import { useStore } from '../state/store'

function fmtFloat(shares: number | null): string {
  if (shares == null) return '?'
  return `${(shares / 1_000_000).toFixed(1)}M`
}

export function ScannerPanel() {
  const scanner = useStore((s) => s.scanner)
  const selected = useStore((s) => s.selected)
  const selectSymbol = useStore((s) => s.selectSymbol)
  const pickers = useStore((s) => s.pickers)
  const activePicker = useStore((s) => s.activePicker)

  const picker = pickers.find((p) => p.name === activePicker)

  return (
    <div className="panel">
      <div className="panel-title">
        <span>Scanner — {picker?.label ?? activePicker}</span>
      </div>
      <div className="scanner-list">
        {scanner.length === 0 && <div className="empty-note">No stocks meet the criteria right now</div>}
        {scanner.map((r) => (
          <div
            key={r.symbol}
            className={`scanner-row ${r.symbol === selected ? 'selected' : ''}`}
            onClick={() => void selectSymbol(r.symbol)}
          >
            <div className="top">
              <span className={`grade grade-${r.grade}`}>{r.grade}</span>
              <span className="sym">{r.symbol}</span>
              <span className="price">${r.price.toFixed(2)}</span>
              <span className={`chg ${r.change_pct >= 0 ? 'pos' : 'neg'}`}>
                {r.change_pct >= 0 ? '+' : ''}{r.change_pct.toFixed(1)}%
              </span>
            </div>
            <div className="meta">
              <span>{r.relative_volume.toFixed(1)}x rvol</span>
              <span>float {fmtFloat(r.float_shares)}</span>
              <span>score {r.score.toFixed(0)}</span>
            </div>
            {r.headline && <div className="headline" title={r.headline}>📰 {r.headline}</div>}
            <div className="checks">
              {r.checks.map((c) => (
                <span key={c.name} className={`check ${c.passed ? 'ok' : ''}`} title={`${c.name}: ${c.value}`}>
                  {c.passed ? '✓' : '✗'} {c.name.split('≥')[0].split('<')[0].trim().slice(0, 14)}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
