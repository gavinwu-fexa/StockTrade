import { useEffect, useState } from 'react'

interface Props {
  params: Record<string, unknown>
  onApply: (params: Record<string, unknown>) => void
  applyLabel?: string
}

/** Generic editor for a strategy's params: numbers get number inputs,
 *  booleans get switches. Types come from the current values. */
export function ParamsEditor({ params, onApply, applyLabel = 'Apply' }: Props) {
  const [draft, setDraft] = useState<Record<string, unknown>>(params)
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    setDraft(params)
    setDirty(false)
  }, [params])

  const setField = (key: string, value: unknown) => {
    setDraft((d) => ({ ...d, [key]: value }))
    setDirty(true)
  }

  const entries = Object.entries(draft)
  if (!entries.length) return null

  return (
    <div className="params-editor">
      {entries.map(([key, value]) => (
        <div className="param-row" key={key}>
          <span className="param-name">{key.replace(/_/g, ' ')}</span>
          {typeof value === 'boolean' ? (
            <div
              className={`switch ${value ? 'on' : ''}`}
              onClick={() => setField(key, !value)}
              role="switch"
              aria-checked={value}
            />
          ) : (
            <input
              type="number"
              step="any"
              value={String(value)}
              onChange={(e) => setField(key, e.target.value === '' ? 0 : Number(e.target.value))}
            />
          )}
        </div>
      ))}
      {dirty && (
        <button className="btn-run btn-apply" onClick={() => { onApply(draft); setDirty(false) }}>
          {applyLabel}
        </button>
      )}
    </div>
  )
}
