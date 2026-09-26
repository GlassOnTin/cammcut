import { useState } from 'react'
import { useStore, uid } from '../store'
import { SHAPES, type ShapeDef } from '../shapes'

/** Shape library: parametric generators, one click adds to a "shapes" layer. */
export default function ShapesPanel() {
  const [openId, setOpenId] = useState<string | null>(null)

  function add(shape: ShapeDef, params: Record<string, number>) {
    const st = useStore.getState()
    if (!st.doc) return
    const d = shape.make(params)
    // place at the centre of the current view
    const v = st.view
    const tx = v.x + v.w / 2
    const ty = v.y + v.h / 2
    const item = { id: uid(), kind: 'path' as const, d, transform: [1, 0, 0, 1, tx, ty] }
    st.insertItems('shapes', [item])
  }

  return (
    <div className="panel shapes-panel">
      <div className="panel-title">Shapes</div>
      {SHAPES.map((s) => (
        <div key={s.id} className="shape-row">
          <button
            className="shape-btn"
            onClick={() => add(s, Object.fromEntries(s.params.map((p) => [p.key, p.def])))}
          >
            {s.label}
          </button>
          <button
            className="shape-cfg"
            title="set sizes first"
            aria-label={`${s.label} options`}
            onClick={() => (openId === s.id ? setOpenId(null) : setOpenId(s.id))}
          >
            {openId === s.id ? '▾' : '▸'}
          </button>
        </div>
      ))}
      {openId && SHAPES.filter((s) => s.id === openId).map((s) => (
        <ShapeForm key={s.id} shape={s} onAdd={(p) => { add(s, p); setOpenId(null) }} />
      ))}
      <div className="hint">tap a shape to place it at the view centre, then drag it · ▸ sets sizes first</div>
    </div>
  )
}

function ShapeForm({ shape, onAdd }: { shape: ShapeDef; onAdd: (p: Record<string, number>) => void }) {
  const [params, setParams] = useState<Record<string, number>>(
    () => Object.fromEntries(shape.params.map((p) => [p.key, p.def])),
  )
  const [previewD, setPreviewD] = useState(() => shape.make(
    Object.fromEntries(shape.params.map((p) => [p.key, p.def])),
  ))

  function update(key: string, value: number, all: Record<string, number>) {
    const next = { ...all, [key]: value }
    setParams(next)
    try {
      setPreviewD(shape.make(next))
    } catch {
      /* keep last good preview */
    }
  }

  return (
    <div className="shape-form">
      <svg viewBox="-30 -30 60 60" className="shape-preview">
        <path d={previewD} fill="#bae6fd" fillOpacity={0.45} stroke="#0369a1" strokeWidth={1} />
      </svg>
      {shape.params.map((p) => (
        <label key={p.key} className="field">
          {p.label}
          <input
            type="number" value={params[p.key]} min={p.min} max={p.max} step="any"
            onChange={(e) => update(p.key, parseFloat(e.target.value) || 0, params)}
          />
        </label>
      ))}
      <button className="shape-add" onClick={() => onAdd(params)}>add to artboard</button>
    </div>
  )
}