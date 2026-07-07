import {
  ColorType,
  CrosshairMode,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts'
import { useEffect, useRef } from 'react'
import { useStore } from '../state/store'
import { emaSeries, macdSeries, vwapSeries } from './indicators'

const chartOptions = {
  layout: {
    background: { type: ColorType.Solid, color: '#0b0e14' },
    textColor: '#8891a5',
    fontSize: 10,
  },
  grid: {
    vertLines: { color: '#161b28' },
    horzLines: { color: '#161b28' },
  },
  crosshair: { mode: CrosshairMode.Normal },
  rightPriceScale: { borderColor: '#232a3b' },
  timeScale: {
    borderColor: '#232a3b',
    timeVisible: true,
    secondsVisible: true,
    rightOffset: 4,
  },
}

export function ChartPanel() {
  const selected = useStore((s) => s.selected)
  const bars = useStore((s) => s.bars)
  const quote = useStore((s) => s.quote)
  const staged = useStore((s) => s.staged)
  const positions = useStore((s) => s.positions)

  const mainRef = useRef<HTMLDivElement>(null)
  const macdRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const macdChartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<{
    candles: ISeriesApi<'Candlestick'>
    volume: ISeriesApi<'Histogram'>
    emaFast: ISeriesApi<'Line'>
    emaSlow: ISeriesApi<'Line'>
    vwap: ISeriesApi<'Line'>
    macd: ISeriesApi<'Line'>
    macdSignal: ISeriesApi<'Line'>
    macdHist: ISeriesApi<'Histogram'>
  } | null>(null)
  const syncing = useRef(false)

  useEffect(() => {
    if (!mainRef.current || !macdRef.current) return

    const chart = createChart(mainRef.current, chartOptions)
    const macdChart = createChart(macdRef.current, {
      ...chartOptions,
      timeScale: { ...chartOptions.timeScale, visible: false },
    })
    chartRef.current = chart
    macdChartRef.current = macdChart

    const candles = chart.addCandlestickSeries({
      upColor: '#26a69a', downColor: '#ef5350',
      wickUpColor: '#26a69a', wickDownColor: '#ef5350',
      borderVisible: false,
    })
    const volume = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    })
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })

    const emaFast = chart.addLineSeries({
      color: '#4f8ef7', lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
    })
    const emaSlow = chart.addLineSeries({
      color: '#ffb74d', lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
    })
    const vwap = chart.addLineSeries({
      color: '#b388ff', lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false,
    })

    const macdHist = macdChart.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false })
    const macd = macdChart.addLineSeries({
      color: '#4f8ef7', lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
    })
    const macdSignal = macdChart.addLineSeries({
      color: '#ffb74d', lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
    })

    seriesRef.current = { candles, volume, emaFast, emaSlow, vwap, macd, macdSignal, macdHist }

    // keep the two time scales in lockstep
    const sync = (from: IChartApi, to: IChartApi) => {
      from.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (syncing.current || !range) return
        syncing.current = true
        to.timeScale().setVisibleLogicalRange(range)
        syncing.current = false
      })
    }
    sync(chart, macdChart)
    sync(macdChart, chart)

    const resize = () => {
      if (mainRef.current) chart.applyOptions({
        width: mainRef.current.clientWidth, height: mainRef.current.clientHeight,
      })
      if (macdRef.current) macdChart.applyOptions({
        width: macdRef.current.clientWidth, height: macdRef.current.clientHeight,
      })
    }
    const ro = new ResizeObserver(resize)
    ro.observe(mainRef.current)
    resize()

    return () => {
      ro.disconnect()
      chart.remove()
      macdChart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [])

  // full redraw when bars change (bar list is small; setData is cheap enough)
  useEffect(() => {
    const s = seriesRef.current
    if (!s) return
    const t = (ts: number) => ts as UTCTimestamp
    s.candles.setData(bars.map((b) => ({
      time: t(b.ts), open: b.open, high: b.high, low: b.low, close: b.close,
    })))
    s.volume.setData(bars.map((b) => ({
      time: t(b.ts), value: b.volume,
      color: b.close >= b.open ? 'rgba(38,166,154,0.4)' : 'rgba(239,83,80,0.4)',
    })))
    s.emaFast.setData(emaSeries(bars, 9).map((p) => ({ time: t(p.time), value: p.value })))
    s.emaSlow.setData(emaSeries(bars, 20).map((p) => ({ time: t(p.time), value: p.value })))
    s.vwap.setData(vwapSeries(bars).map((p) => ({ time: t(p.time), value: p.value })))

    const m = macdSeries(bars)
    s.macd.setData(m.filter((p) => p.macd !== null).map((p) => ({ time: t(p.time), value: p.macd! })))
    s.macdSignal.setData(m.filter((p) => p.signal !== null).map((p) => ({ time: t(p.time), value: p.signal! })))
    s.macdHist.setData(m.filter((p) => p.hist !== null).map((p) => ({
      time: t(p.time), value: p.hist!,
      color: p.hist! >= 0 ? 'rgba(38,166,154,0.55)' : 'rgba(239,83,80,0.55)',
    })))
  }, [bars])

  // position average-price line
  const posLineRef = useRef<ReturnType<ISeriesApi<'Candlestick'>['createPriceLine']> | null>(null)
  useEffect(() => {
    const s = seriesRef.current
    if (!s) return
    if (posLineRef.current) {
      s.candles.removePriceLine(posLineRef.current)
      posLineRef.current = null
    }
    const pos = positions.find((p) => p.symbol === selected)
    if (pos && pos.qty > 0) {
      posLineRef.current = s.candles.createPriceLine({
        price: pos.avg_price,
        color: '#4f8ef7',
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: `${pos.qty} @ ${pos.avg_price.toFixed(2)}`,
      })
    }
  }, [positions, selected, bars.length > 0])

  const pos = positions.find((p) => p.symbol === selected)

  return (
    <div className="panel chart-panel">
      <div className="chart-header">
        <span className="sym">{selected ?? '—'}</span>
        {quote && (
          <span className="quote-line">
            <span>Bid <b className="neg">{quote.bid.toFixed(2)}</b></span>
            <span>Ask <b className="pos">{quote.ask.toFixed(2)}</b></span>
            <span>Last <b>{quote.last.toFixed(2)}</b></span>
            {pos && pos.qty > 0 && (
              <span>
                P&L{' '}
                <b className={pos.unrealized_pnl >= 0 ? 'pos' : 'neg'}>
                  {pos.unrealized_pnl >= 0 ? '+' : ''}
                  {pos.unrealized_pnl.toFixed(2)}
                </b>
              </span>
            )}
          </span>
        )}
      </div>
      <div className="chart-container">
        <div className="legend">
          <span className="k" style={{ color: '#4f8ef7' }}>EMA9</span>
          <span className="k" style={{ color: '#ffb74d' }}>EMA20</span>
          <span className="k" style={{ color: '#b388ff' }}>VWAP</span>
          <span className="k" style={{ color: '#5a6376' }}>MACD 12·26·9 below</span>
        </div>
        {staged && (
          <div className={`staged ${staged.side}`}>
            <span className={`side ${staged.side === 'buy' ? 'pos' : 'neg'}`}>{staged.side}</span>
            <span>{staged.qty} {staged.symbol} @ ${staged.limitPrice.toFixed(2)} LMT</span>
            <span className="hint">↑↓ price · Enter send · Esc cancel</span>
          </div>
        )}
        <div ref={mainRef} className="chart-main" />
        <div ref={macdRef} className="chart-macd" />
      </div>
    </div>
  )
}
