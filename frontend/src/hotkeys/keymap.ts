// Central hotkey definitions. Edit `combo` values to remap.
// Combos: "shift+b", "b", "arrowup", "1", "?" etc. (lowercase key names)

export interface HotkeyDef {
  combo: string
  action: string
  label: string
  group: 'Trading' | 'Orders' | 'Sizing' | 'Navigation'
  danger?: boolean
}

export const KEYMAP: HotkeyDef[] = [
  { combo: 'shift+b', action: 'buyMarket', label: 'Buy market (current share size)', group: 'Trading' },
  { combo: 'shift+s', action: 'sellHalf', label: 'Sell 1/2 position (market)', group: 'Trading' },
  { combo: 'shift+f', action: 'flattenSelected', label: 'Flatten current symbol', group: 'Trading' },
  { combo: 'shift+x', action: 'panic', label: 'PANIC: flatten all + cancel all (press twice)', group: 'Trading', danger: true },
  { combo: 'shift+c', action: 'cancelAll', label: 'Cancel all open orders', group: 'Orders' },
  { combo: 'b', action: 'stageBuy', label: 'Stage limit buy at ask', group: 'Orders' },
  { combo: 's', action: 'stageSell', label: 'Stage limit sell at bid', group: 'Orders' },
  { combo: 'enter', action: 'sendStaged', label: 'Send staged order', group: 'Orders' },
  { combo: 'escape', action: 'clearStaged', label: 'Clear staged order', group: 'Orders' },
  { combo: 'arrowup', action: 'nudgeUp', label: 'Nudge staged price +1¢', group: 'Orders' },
  { combo: 'arrowdown', action: 'nudgeDown', label: 'Nudge staged price −1¢', group: 'Orders' },
  { combo: '1', action: 'size25', label: 'Size = 25% of cash', group: 'Sizing' },
  { combo: '2', action: 'size50', label: 'Size = 50% of cash', group: 'Sizing' },
  { combo: '3', action: 'size75', label: 'Size = 75% of cash', group: 'Sizing' },
  { combo: '4', action: 'size100', label: 'Size = 100% of cash', group: 'Sizing' },
  { combo: 'tab', action: 'nextSymbol', label: 'Next scanner symbol', group: 'Navigation' },
  { combo: 'shift+tab', action: 'prevSymbol', label: 'Previous scanner symbol', group: 'Navigation' },
  { combo: '?', action: 'toggleHelp', label: 'Show/hide this help', group: 'Navigation' },
]

export function comboOf(e: KeyboardEvent): string {
  const parts: string[] = []
  if (e.ctrlKey) parts.push('ctrl')
  if (e.metaKey) parts.push('meta')
  if (e.altKey) parts.push('alt')
  const key = e.key.toLowerCase()
  // '?' already implies shift on most layouts; don't double-encode it
  if (e.shiftKey && key !== '?') parts.push('shift')
  parts.push(key)
  return parts.join('+')
}
