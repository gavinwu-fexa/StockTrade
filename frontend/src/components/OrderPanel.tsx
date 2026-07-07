import { useState } from 'react'
import { useStore } from '../state/store'
import { ParamsEditor } from './ParamsEditor'

export function OrderPanel() {
  const [showParams, setShowParams] = useState(false)
  const shareSize = useStore((s) => s.shareSize)
  const setShareSize = useStore((s) => s.setShareSize)
  const sizePreset = useStore((s) => s.sizePreset)
  const buyMarket = useStore((s) => s.buyMarket)
  const sellHalf = useStore((s) => s.sellHalf)
  const flattenSelected = useStore((s) => s.flattenSelected)
  const autoTrade = useStore((s) => s.autoTrade)
  const setAutoTrade = useStore((s) => s.setAutoTrade)
  const strategies = useStore((s) => s.strategies)
  const activeStrategy = useStore((s) => s.activeStrategy)
  const setStrategy = useStore((s) => s.setStrategy)
  const marketCondition = useStore((s) => s.marketCondition)
  const setMarketCondition = useStore((s) => s.setMarketCondition)
  const strategyParams = useStore((s) => s.strategyParams)
  const setStrategyParams = useStore((s) => s.setStrategyParams)

  return (
    <div className="order-panel">
      <div className="size-row">
        <input
          type="number"
          value={shareSize}
          min={1}
          onChange={(e) => setShareSize(Number(e.target.value))}
          aria-label="Share size"
        />
        {[0.25, 0.5, 0.75, 1].map((f, i) => (
          <button key={f} className="preset-btn" onClick={() => sizePreset(f)} title={`Hotkey: ${i + 1}`}>
            {f * 100}%
          </button>
        ))}
      </div>
      <div className="btn-row">
        <button className="btn btn-buy" onClick={() => void buyMarket()}>
          BUY<small>⇧B market</small>
        </button>
        <button className="btn btn-sell" onClick={() => void sellHalf()}>
          SELL ½<small>⇧S market</small>
        </button>
        <button className="btn btn-flat" onClick={() => void flattenSelected()}>
          FLAT<small>⇧F symbol</small>
        </button>
      </div>
      <div className="toggle-row">
        <span>
          Strategy{' '}
          <span className="param-toggle" onClick={() => setShowParams(!showParams)}>
            {showParams ? '▾ params' : '▸ params'}
          </span>
        </span>
        <select value={activeStrategy} onChange={(e) => void setStrategy(e.target.value)}>
          {strategies.map((st) => (
            <option key={st.name} value={st.name}>{st.label}</option>
          ))}
        </select>
      </div>
      {showParams && (
        <ParamsEditor params={strategyParams} onApply={(p) => void setStrategyParams(p)} />
      )}
      <div className="toggle-row">
        <span>Auto-trade signals</span>
        <div
          className={`switch ${autoTrade ? 'on' : ''}`}
          onClick={() => setAutoTrade(!autoTrade)}
          role="switch"
          aria-checked={autoTrade}
        />
      </div>
      <div className="toggle-row">
        <span>Market condition</span>
        <select value={marketCondition} onChange={(e) => void setMarketCondition(e.target.value)}>
          <option value="hot">Hot (float &lt; 20M)</option>
          <option value="cold">Cold (float &lt; 10M)</option>
        </select>
      </div>
    </div>
  )
}
