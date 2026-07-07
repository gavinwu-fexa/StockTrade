import { useEffect } from 'react'
import { ChartPanel } from './components/ChartPanel'
import { Header } from './components/Header'
import { HotkeyHelp } from './components/HotkeyHelp'
import { RightPanel } from './components/RightPanel'
import { ScannerPanel } from './components/ScannerPanel'
import { Toasts } from './components/Toasts'
import { useHotkeys } from './hotkeys/useHotkeys'
import { useStore } from './state/store'

export default function App() {
  const init = useStore((s) => s.init)
  useHotkeys()

  useEffect(() => {
    init()
  }, [])

  return (
    <div className="app">
      <Header />
      <div className="main">
        <ScannerPanel />
        <ChartPanel />
        <RightPanel />
      </div>
      <HotkeyHelp />
      <Toasts />
    </div>
  )
}
