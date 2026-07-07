// Client-side indicator computation for chart overlays.
import type { Bar } from '../types'

export interface LinePoint { time: number; value: number }

export function emaSeries(bars: Bar[], period: number): LinePoint[] {
  const out: LinePoint[] = []
  let ema: number | null = null
  const k = 2 / (period + 1)
  const seed: number[] = []
  for (const b of bars) {
    if (ema === null) {
      seed.push(b.close)
      if (seed.length >= period) ema = seed.reduce((a, x) => a + x, 0) / seed.length
      else continue
    } else {
      ema = (b.close - ema) * k + ema
    }
    out.push({ time: b.ts, value: ema })
  }
  return out
}

export function vwapSeries(bars: Bar[]): LinePoint[] {
  const out: LinePoint[] = []
  let cumPV = 0
  let cumVol = 0
  for (const b of bars) {
    const typical = (b.high + b.low + b.close) / 3
    cumPV += typical * b.volume
    cumVol += b.volume
    if (cumVol > 0) out.push({ time: b.ts, value: cumPV / cumVol })
  }
  return out
}

export interface MacdPoint {
  time: number
  macd: number | null
  signal: number | null
  hist: number | null
}

export function macdSeries(bars: Bar[], fast = 12, slow = 26, signalP = 9): MacdPoint[] {
  const out: MacdPoint[] = []
  const k = (p: number) => 2 / (p + 1)
  let emaF: number | null = null
  let emaS: number | null = null
  let emaSig: number | null = null
  const seedF: number[] = []
  const seedS: number[] = []
  const seedSig: number[] = []

  for (const b of bars) {
    if (emaF === null) {
      seedF.push(b.close)
      if (seedF.length >= fast) emaF = seedF.reduce((a, x) => a + x, 0) / seedF.length
    } else emaF = (b.close - emaF) * k(fast) + emaF

    if (emaS === null) {
      seedS.push(b.close)
      if (seedS.length >= slow) emaS = seedS.reduce((a, x) => a + x, 0) / seedS.length
    } else emaS = (b.close - emaS) * k(slow) + emaS

    let macd: number | null = null
    if (emaF !== null && emaS !== null) {
      macd = emaF - emaS
      if (emaSig === null) {
        seedSig.push(macd)
        if (seedSig.length >= signalP) emaSig = seedSig.reduce((a, x) => a + x, 0) / seedSig.length
      } else emaSig = (macd - emaSig) * k(signalP) + emaSig
    }
    out.push({
      time: b.ts,
      macd,
      signal: emaSig,
      hist: macd !== null && emaSig !== null ? macd - emaSig : null,
    })
  }
  return out
}
