import { useEffect, useRef } from 'react'
import { useStore } from '../state/store'
import { KEYMAP, comboOf } from './keymap'

const PANIC_WINDOW_MS = 1500

export function useHotkeys() {
  const panicArmed = useRef<number | null>(null)

  useEffect(() => {
    const byCombo = new Map(KEYMAP.map((d) => [d.combo, d]))

    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      const typing = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' ||
        target.tagName === 'SELECT' || target.isContentEditable
      if (typing && e.key !== 'Escape') return

      const def = byCombo.get(comboOf(e))
      if (!def) return
      e.preventDefault()

      const s = useStore.getState()
      switch (def.action) {
        case 'buyMarket': void s.buyMarket(); break
        case 'sellHalf': void s.sellHalf(); break
        case 'flattenSelected': void s.flattenSelected(); break
        case 'panic': {
          const now = Date.now()
          if (panicArmed.current && now - panicArmed.current < PANIC_WINDOW_MS) {
            panicArmed.current = null
            void s.flattenAll()
          } else {
            panicArmed.current = now
            s.toast('warn', 'Press Shift+X again to FLATTEN EVERYTHING')
          }
          break
        }
        case 'cancelAll': void s.cancelAll(); break
        case 'stageBuy': s.stageOrder('buy'); break
        case 'stageSell': s.stageOrder('sell'); break
        case 'sendStaged': void s.sendStaged(); break
        case 'clearStaged':
          if (s.helpOpen) s.setHelpOpen(false)
          else s.clearStaged()
          break
        case 'nudgeUp': s.nudgeStaged(1); break
        case 'nudgeDown': s.nudgeStaged(-1); break
        case 'size25': s.sizePreset(0.25); break
        case 'size50': s.sizePreset(0.5); break
        case 'size75': s.sizePreset(0.75); break
        case 'size100': s.sizePreset(1.0); break
        case 'nextSymbol': s.cycleSymbol(1); break
        case 'prevSymbol': s.cycleSymbol(-1); break
        case 'toggleHelp': s.setHelpOpen(!s.helpOpen); break
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])
}
