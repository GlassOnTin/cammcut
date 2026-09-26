import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { useStore } from '../store'
import type { Item, TidyCheck, TidyOp } from '../types'

/** Document checks and tidy ops. Checks run automatically against the whole
 *  document (all layers, visible or not); ops replace every item. */
export default function TidyPanel() {
  const doc = useStore((s) => s.doc)
  const [check, setCheck] = useState<TidyCheck | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [tol, setTol] = useState(0.05)
  const [chord, setChord] = useState(0.1)

  const allItems: Item[] = doc ? doc.layers.flatMap((l) => l.items) : []

  const runCheck = useCallback(() => {
    if (allItems.length === 0) { setCheck(null); return }
    const n = allItems.length
    api.tidyCheck(allItems)
      .then((r) => { if (allItems.length === n) setCheck(r) })
      .catch((e) => setError(String(e.message ?? e)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc])

  useEffect(() => {
    const t = setTimeout(runCheck, 400)
    return () => clearTimeout(t)
  }, [runCheck])

  async function apply(ops: TidyOp[], msg: string) {
    if (!doc || allItems.length === 0) return
    setBusy(true)
    setError('')
    try {
      const r = await api.tidyApply(allItems, ops)
      useStore.getState().commit()
      // distribute the returned items back over the layers, in order
      let k = 0
      const layers = doc.layers.map((l) => ({
        ...l,
        items: l.items.map(() => r.items[k++]),
      }))
      useStore.getState().setDoc({ ...doc, layers })
      setNote(`${msg} (${r.report.map((x) => `${x.op}: ${x.changed}`).join(', ')})`)
      setCheck(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const clean = check && check.open_subpaths === 0 && check.duplicate_points === 0
    && check.self_crossings === 0

  return (
    <div className="panel shapes-panel">
      <div className="panel-title">Tidy</div>
      <div className="hint">checks run on the whole document (every layer)</div>
      {error && <div className="error">{error}</div>}
      {!check && !error && <div className="hint">{allItems.length === 0 ? 'nothing to check' : 'checking…'}</div>}
      {check && (
        <div className="check-results">
          <div className={check.open_subpaths ? 'stat warn' : 'stat'}>
            {check.open_subpaths} open subpath{check.open_subpaths === 1 ? '' : 's'}
          </div>
          <div className={check.duplicate_points ? 'stat warn' : 'stat'}>
            {check.duplicate_points} duplicate point{check.duplicate_points === 1 ? '' : 's'}
          </div>
          <div className={check.self_crossings ? 'stat warn' : 'stat'}>
            {check.self_crossings} self-crossing{check.self_crossings === 1 ? '' : 's'}
          </div>
          {check.crossing_examples.map((x, i) => <div key={i} className="hint">{x}</div>)}
          {clean && <div className="hint">no issues found</div>}
        </div>
      )}
      <div className="tidy-ops">
        <button className="shape-add" disabled={busy || !check || check.open_subpaths === 0}
          onClick={() => apply([{ op: 'close_paths' }], 'closed open paths')}>
          close open paths
        </button>
        <div className="hint">closing adds a straight cut back to the subpath start</div>
        <button className="shape-add" disabled={busy || !check || check.duplicate_points === 0}
          onClick={() => apply([{ op: 'dedupe_points' }], 'removed duplicate points')}>
          remove duplicate points
        </button>
        <label className="field">
          simplify tolerance mm
          <input type="number" value={tol} min={0.001} max={5} step="any"
            onChange={(e) => setTol(parseFloat(e.target.value) || 0.05)} />
        </label>
        <button className="shape-add" disabled={busy || allItems.length === 0}
          onClick={() => apply([{ op: 'simplify', params: { tol_mm: tol } }], 'simplified')}>
          simplify paths
        </button>
        <div className="hint">simplify bakes curves into line segments at the tolerance</div>
        <label className="field">
          flatten chord mm
          <input type="number" value={chord} min={0.001} max={5} step="any"
            onChange={(e) => setChord(parseFloat(e.target.value) || 0.1)} />
        </label>
        <button className="shape-add" disabled={busy || allItems.length === 0}
          onClick={() => apply([{ op: 'flatten', params: { chord_mm: chord } }], 'flattened')}>
          flatten curves
        </button>
      </div>
      {note && <div className="hint">{note}</div>}
      <div className="hint">crossing detection finds proper crossings only — tangential touches are missed</div>
    </div>
  )
}