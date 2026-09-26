import { useEffect, useState } from 'react'
import { api } from '../api'
import { useStore } from '../store'
import type { JobSettings, Preview } from '../types'

export default function PreviewPanel() {
  const doc = useStore((s) => s.doc)
  const settings = useStore((s) => s.jobSettings)
  const setJobSettings = useStore((s) => s.setJobSettings)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!doc) return
    const itemCount = doc.layers.reduce((n, l) => n + l.items.length, 0)
    if (itemCount === 0) {
      setPreview(null)
      setError(null)
      return
    }
    setBusy(true)
    const t = setTimeout(() => {
      api
        .composePreview(doc, settings)
        .then((p) => {
          setPreview(p)
          setError(null)
        })
        .catch((e) => {
          setPreview(null)
          setError((e as Error).message)
        })
        .finally(() => setBusy(false))
    }, 300)
    return () => clearTimeout(t)
  }, [doc, settings])

  if (!doc) return null
  const num = (k: keyof JobSettings, step: number, label: string) => (
    <label className="field">
      {label}
      <input
        type="number"
        step={step}
        value={settings[k] as number}
        onChange={(e) => setJobSettings({ [k]: Number(e.target.value) })}
      />
    </label>
  )

  return (
    <div className="panel">
      <div className="panel-title">Cut preview</div>
      <div className="field-grid">
        {num('speed', 1, 'speed cm/s')}
        {num('x_mm', 1, 'offset x mm')}
        {num('y_mm', 1, 'offset y mm')}
        {num('scale', 0.05, 'scale')}
        {num('media_w_mm', 1, 'media width mm')}
        {num('media_h_mm', 1, 'media length mm')}
        <label className="field">
          origin
          <select value={settings.origin} onChange={(e) => setJobSettings({ origin: e.target.value as 'content' | 'artboard' })}>
            <option value="content">content</option>
            <option value="artboard">artboard</option>
          </select>
        </label>
        <label className="field check">
          <input type="checkbox" checked={settings.mirror} onChange={(e) => setJobSettings({ mirror: e.target.checked })} />
          mirror
        </label>
      </div>
      <div className="hint">
        the marked “cut origin” corner on the canvas lands on the machine origin + offsets
        — with origin&nbsp;content that is the artwork’s own lower-left, with artboard the artboard corner
      </div>
      {error && <div className="error">{error}</div>}
      {!error && !preview && !busy && <div className="hint">place something on the artboard to see the cut preview</div>}
      {preview && (
        <>
          <div className="stats">
            cut {preview.cut_len_mm} mm · travel {preview.travel_len_mm} mm · ≈{Math.round(preview.est_seconds)} s · {preview.byte_len} bytes
          </div>
          {preview.violations.length > 0 && (
            <div className="error">
              {preview.violations.map((v, i) => (
                <div key={i}>{v.axis}: {v.detail}</div>
              ))}
            </div>
          )}
          <div className="toolpath" dangerouslySetInnerHTML={{ __html: preview.toolpath_svg }} />
        </>
      )}
      {busy && <div className="hint">computing…</div>}
    </div>
  )
}