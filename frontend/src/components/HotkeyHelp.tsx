import { useStore } from '../state/store'
import { KEYMAP } from '../hotkeys/keymap'

const GROUPS = ['Trading', 'Orders', 'Sizing', 'Navigation'] as const

function pretty(combo: string): string {
  return combo
    .replace('shift+', '⇧')
    .replace('arrowup', '↑')
    .replace('arrowdown', '↓')
    .replace('escape', 'Esc')
    .replace('enter', '⏎')
    .replace('tab', 'Tab')
    .toUpperCase()
    .replace('⇧', '⇧')
}

export function HotkeyHelp() {
  const open = useStore((s) => s.helpOpen)
  const setHelpOpen = useStore((s) => s.setHelpOpen)
  if (!open) return null
  return (
    <div className="help-overlay" onClick={() => setHelpOpen(false)}>
      <div className="help-card" onClick={(e) => e.stopPropagation()}>
        <h2>Keyboard shortcuts</h2>
        <div className="sub">Hotkeys are disabled while typing in an input field. Edit src/hotkeys/keymap.ts to remap.</div>
        <div className="help-groups">
          {GROUPS.map((g) => (
            <div className="help-group" key={g}>
              <h3>{g}</h3>
              {KEYMAP.filter((d) => d.group === g).map((d) => (
                <div className={`help-row ${d.danger ? 'danger' : ''}`} key={d.combo}>
                  <span>{d.label}</span>
                  <kbd>{pretty(d.combo)}</kbd>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
