import { useEffect, useState } from 'react'
import { useStore } from '../store'
import { selectionBox } from '../geom/docBox'
import { type Mat, rotateAbout, scaleAbout } from '../geom/matrix'

type Field = 'x' | 'y' | 'w' | 'h'

/** Numeric inspector: position and size of the selection in mm. */
export default function Inspector() {
  const doc = useStore((s) => s.doc)
  const selection = useStore((s) => s.selection)
  const [vals, setVals] = useState<Record<Field, string>>({ x: '', y: '', w: '', h: '' })

  const box = doc && selection.length ? selectionBox(doc, selection) : null

  useEffect(() => {
    if (box) {
      setVals({
        x: box.x.toFixed(2), y: box.y.toFixed(2),
        w: box.w.toFixed(2), h: box.h.toFixed(2),
      })
    } else {
      setVals({ x: '', y: '', w: '', h: '' })
    }
  }, [box?.x, box?.y, box?.w, box?.h]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!doc || !box) {
    return (
      <div className="panel inspector">
        <div className="panel-title">Position</div>
        <div className="hint">nothing selected</div>
      </div>
    )
  }

  // snapshot the transforms the edit starts from
  const orig = () => {
    const updates: Record<string, number[]> = {}
    for (const id of selection) {
      for (const l of doc.layers) {
        const it = l.items.find((i) => i.id === id)
        if (it) updates[id] = [...it.transform]
      }
    }
    return updates
  }

  function apply(field: Field, raw: string) {
    const v = parseFloat(raw)
    if (!Number.isFinite(v)) return
    const st = useStore.getState()
    st.commit()
    const updates = orig()
    if (field === 'x' || field === 'y') {
      const d = field === 'x' ? v - box!.x : v - box!.y
      for (const id of Object.keys(updates)) {
        const t = updates[id]
        updates[id] = [
          t[0], t[1], t[2], t[3],
          t[4] + (field === 'x' ? d : 0), t[5] + (field === 'y' ? d : 0),
        ]
      }
      st.setItemTransforms(updates)
    } else {
      const cur = field === 'w' ? box!.w : box!.h
      if (cur < 1e-6) return
      const s = Math.min(100, Math.max(0.01, v / cur))
      // scale about the top-left corner so x/y stay put
      const m = scaleAbout(field === 'w' ? s : 1, field === 'h' ? s : 1, box!.x, box!.y)
      for (const id of Object.keys(updates)) {
        const t = updates[id]
        updates[id] = [
          m[0] * t[0] + m[2] * t[1], m[1] * t[0] + m[3] * t[1],
          m[0] * t[2] + m[2] * t[3], m[1] * t[2] + m[3] * t[3],
          m[0] * t[4] + m[2] * t[5] + m[4], m[1] * t[4] + m[3] * t[5] + m[5],
        ]
      }
      st.setItemTransforms(updates)
    }
  }

  const field = (name: Field, label: string) => (
    <label className="field">
      {label} (mm)
      <input
        type="number" step="0.1" value={vals[name]}
        onChange={(e) => setVals((v) => ({ ...v, [name]: e.target.value }))}
        onBlur={(e) => apply(name, e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
        }}
      />
    </label>
  )

  // mirror/rotate about the centre of the selection's bounding box, so the
  // artwork stays where it is; y-down space makes +90° read as clockwise
  function transformSel(m: Mat) {
    useStore.getState().transformSelection(m, true)
  }
  const cx = box.x + box.w / 2
  const cy = box.y + box.h / 2

  return (
    <div className="panel inspector">
      <div className="panel-title">Position</div>
      <div className="field-grid">
        {field('x', 'X')}
        {field('y', 'Y')}
        {field('w', 'W')}
        {field('h', 'H')}
      </div>
      <div className="sel-actions">
        <button title="mirror horizontally" onClick={() => transformSel(scaleAbout(-1, 1, cx, cy))}>⇋ mirror</button>
        <button title="mirror vertically" onClick={() => transformSel(scaleAbout(1, -1, cx, cy))}>⇅ flip</button>
        <button title="rotate 90° counter-clockwise" onClick={() => transformSel(rotateAbout(-90, cx, cy))}>↺ 90°</button>
        <button title="rotate 90° clockwise" onClick={() => transformSel(rotateAbout(90, cx, cy))}>↻ 90°</button>
      </div>
      <div className="sel-actions">
        <button onClick={() => useStore.getState().duplicateSelection()}>duplicate</button>
        <button className="danger" onClick={() => useStore.getState().deleteSelection()}>delete</button>
        <button onClick={() => useStore.getState().selectAll()}>select all</button>
      </div>
      <div className="hint">
        {selection.length} item{selection.length === 1 ? '' : 's'} selected · values are the
        bounding box of the whole selection
      </div>
    </div>
  )
}