import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { uid, useStore } from '../store'
import type { FontInfo, TextResult } from '../types'

// Quick-insert characters. Emoji need a font with the glyphs — Unifont covers
// most; other fonts will warn "glyphs missing from font and skipped".
const QUICK: string[] = ['✂', '★', '♥', '♦', '♪', '✉', '⚠', '😀', '🎉', '👍']

/** Text → outline paths via /api/text. Preview renders the exact cut geometry. */
export default function TextPanel() {
  const [fonts, setFonts] = useState<FontInfo[]>([])
  const [text, setText] = useState('HELLO')
  const [fontId, setFontId] = useState('')
  const [size, setSize] = useState(20)
  const [tracking, setTracking] = useState(0)
  const [result, setResult] = useState<TextResult | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const seq = useRef(0)

  useEffect(() => {
    if (fonts.length > 0) return
    api.listFonts().then((fs) => {
      setFonts(fs)
      const dejavu = fs.find((f) => f.path.endsWith('DejaVuSans.ttf'))
      setFontId((cur) => cur || (dejavu ?? fs[0])?.id || '')
    }).catch((e) => setError(String(e.message ?? e)))
  }, [fonts, setFonts])

  // debounced outline preview — same endpoint that insert uses, so the
  // preview is exactly what gets cut
  useEffect(() => {
    if (!text || !fontId) { setResult(null); return }
    const n = ++seq.current
    setBusy(true)
    const t = setTimeout(() => {
      api.textToPath(text, fontId, size, tracking)
        .then((r) => { if (seq.current === n) { setResult(r); setError('') } })
        .catch((e) => { if (seq.current === n) { setResult(null); setError(String(e.message ?? e)) } })
        .finally(() => { if (seq.current === n) setBusy(false) })
    }, 250)
    return () => clearTimeout(t)
  }, [text, fontId, size, tracking])

  const families = useMemo(() => {
    const map = new Map<string, FontInfo[]>()
    for (const f of fonts) {
      const list = map.get(f.family) ?? []
      list.push(f)
      map.set(f.family, list)
    }
    return [...map.entries()]
  }, [fonts])

  function insert() {
    if (!result) return
    const st = useStore.getState()
    if (!st.doc) return
    // the generated 'd' has its pen origin at (0,0) baseline; bounds are
    // x_mm/y_mm/w/h in the same space — centre the bbox on the view centre
    const v = st.view
    const e = v.x + v.w / 2 - (result.x_mm + result.width_mm / 2)
    const f = v.y + v.h / 2 - (result.y_mm + result.height_mm / 2)
    const items = result.items.map((it) => ({
      id: uid(), kind: 'path' as const, d: it.d, transform: [1, 0, 0, 1, e, f],
    }))
    st.insertItems('text', items)
  }

  const hasEmoji = /\p{Extended_Pictographic}/u.test(text)
  const fontHasName = fonts.find((f) => f.id === fontId)?.family.toLowerCase().includes('unifont')

  return (
    <div className="panel shapes-panel">
      <div className="panel-title">Text</div>
      <label className="field">
        font
        <select value={fontId} onChange={(e) => setFontId(e.target.value)}>
          {families.map(([fam, list]) => (
            <optgroup key={fam} label={fam}>
              {list.map((f) => (
                <option key={f.id} value={f.id}>{fam} {f.style}</option>
              ))}
            </optgroup>
          ))}
        </select>
      </label>
      <label className="field">
        text
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="text to cut" />
      </label>
      <div className="field-row">
        <label className="field">
          size mm
          <input type="number" value={size} min={1} max={500} step="any"
            onChange={(e) => setSize(parseFloat(e.target.value) || 1)} />
        </label>
        <label className="field">
          tracking mm
          <input type="number" value={tracking} min={-50} max={50} step="any"
            onChange={(e) => setTracking(parseFloat(e.target.value) || 0)} />
        </label>
      </div>
      <div className="field-row">
        {QUICK.map((ch) => (
          <button key={ch} className="quick-ch" title={`append ${ch}`}
            onClick={() => setText((t) => t + ch)}>{ch}</button>
        ))}
      </div>
      {hasEmoji && !fontHasName && (
        <div className="hint warn">emoji need a font that has them — pick Unifont, otherwise those glyphs are skipped with a warning</div>
      )}
      {error && <div className="error">{error}</div>}
      {result && (
        <div className="text-preview">
          <svg viewBox={`${result.x_mm} ${result.y_mm} ${Math.max(result.width_mm, 0.1)} ${Math.max(result.height_mm, 0.1)}`}
            className="shape-preview" style={{ height: 90 }}>
            <path d={result.items[0].d} fill="none" stroke="#0369a1" strokeWidth={Math.max(result.width_mm, result.height_mm) / 80} />
          </svg>
          <div className="hint">{result.width_mm.toFixed(1)} × {result.height_mm.toFixed(1)} mm</div>
          {result.warnings.map((w, i) => <div key={i} className="hint warn">{w}</div>)}
        </div>
      )}
      {busy && <div className="hint">converting…</div>}
      <button className="shape-add" disabled={!result} onClick={insert}>
        add to artboard
      </button>
    </div>
  )
}