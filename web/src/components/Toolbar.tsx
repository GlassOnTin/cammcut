import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useStore } from '../store'

export default function Toolbar() {
  const doc = useStore((s) => s.doc)
  const status = useStore((s) => s.status)
  const savedMtime = useStore((s) => s.savedMtime)
  const newProject = useStore((s) => s.newProject)
  const openProject = useStore((s) => s.openProject)
  const save = useStore((s) => s.save)
  const renameProject = useStore((s) => s.renameProject)
  const deleteProject = useStore((s) => s.deleteProject)
  const undo = useStore((s) => s.undo)
  const redo = useStore((s) => s.redo)
  const setArtboard = useStore((s) => s.setArtboard)
  const fitView = useStore((s) => s.fitView)
  const [projects, setProjects] = useState<{ id: string; name: string }[]>([])
  const [showOpen, setShowOpen] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const [w, setW] = useState('584')
  const [h, setH] = useState('300')
  const [name, setName] = useState('')
  const [importMsg, setImportMsg] = useState<string | null>(null)

  useEffect(() => {
    if (doc) {
      setW(String(doc.artboard.w_mm))
      setH(String(doc.artboard.h_mm))
      setName(doc.name)
    }
  }, [doc?.artboard.w_mm, doc?.artboard.h_mm, doc?.name])

  async function commitName() {
    if (doc && name.trim() && name !== doc.name) await renameProject(doc.id, name)
  }

  useEffect(() => {
    if (showOpen) api.listProjects().then(setProjects).catch(() => setProjects([]))
  }, [showOpen])

  async function onImportFile(f: File) {
    if (!doc) return
    try {
      const res = await api.importSvg(f)
      const layerName = f.name.replace(/\.svg$/i, '').slice(0, 40) || 'import'
      useStore.getState().addLayerWithItems(layerName, res.items)
      const warns = res.warnings.length ? ` — ${res.warnings.join('; ')}` : ''
      setImportMsg(`imported ${res.items.length} paths (${res.width_mm}×${res.height_mm} mm)${warns}`)
      fitView()
    } catch (e) {
      setImportMsg(`import failed: ${(e as Error).message}`)
    }
    setTimeout(() => setImportMsg(null), 8000)
  }

  async function doRename(p: { id: string; name: string }) {
    const name = window.prompt('rename project', p.name)
    if (name === null) return
    try {
      await renameProject(p.id, name)
    } catch (e) {
      setImportMsg(`rename failed: ${(e as Error).message}`)
      setTimeout(() => setImportMsg(null), 8000)
    }
    if (showOpen) api.listProjects().then(setProjects).catch(() => {})
  }

  async function doDelete(p: { id: string; name: string }) {
    if (!window.confirm(`delete “${p.name}”? This cannot be undone.`)) return
    try {
      await deleteProject(p.id)
    } catch (e) {
      setImportMsg(`delete failed: ${(e as Error).message}`)
      setTimeout(() => setImportMsg(null), 8000)
    }
    if (showOpen) api.listProjects().then(setProjects).catch(() => {})
  }

  if (!doc) return null

  return (
    <div className="toolbar">
      <button onClick={() => newProject()}>new</button>
      <button onClick={() => setShowOpen(!showOpen)}>open…</button>
      <button onClick={() => save()}>save</button>
      <input
        className="toolbar-name"
        value={name}
        title="project name — Enter or click away to save the rename"
        onChange={(e) => setName(e.target.value)}
        onBlur={commitName}
        onKeyDown={(e) => {
          if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
          if (e.key === 'Escape') setName(doc.name)
        }}
      />
      {savedMtime === 0 && (
        <span className="draft-badge" title="not saved on the server yet — click save to keep it">
          unsaved
        </span>
      )}
      <button onClick={() => undo()} title="undo (ctrl+z)">↩</button>
      <button onClick={() => redo()} title="redo (ctrl+y)">↪</button>
      <button onClick={() => fitView()}>fit</button>
      <span className="toolbar-sep" />
      <label>
        artboard mm
        <input className="num" value={w} onChange={(e) => setW(e.target.value)} onBlur={() => setArtboard(Number(w) || doc.artboard.w_mm, Number(h) || doc.artboard.h_mm)} />
        ×
        <input className="num" value={h} onChange={(e) => setH(e.target.value)} onBlur={() => setArtboard(Number(w) || doc.artboard.w_mm, Number(h) || doc.artboard.h_mm)} />
      </label>
      <span className="toolbar-sep" />
      <button onClick={() => fileRef.current?.click()}>import SVG…</button>
      <input
        ref={fileRef}
        type="file"
        accept=".svg,image/svg+xml"
        style={{ display: 'none' }}
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) onImportFile(f)
          e.target.value = ''
        }}
      />
      {importMsg && <span className="toolbar-msg">{importMsg}</span>}
      {showOpen && (
        <div className="open-menu">
          {projects.length === 0 && <div className="hint">no saved projects</div>}
          {projects.map((p) => (
            <div key={p.id} className="open-row">
              <button
                className="open-name"
                onClick={() => {
                  openProject(p.id)
                  setShowOpen(false)
                }}
              >
                {p.name}
              </button>
              <button className="open-act" title="rename" onClick={() => doRename(p)}>✎</button>
              <button className="open-act danger" title="delete" onClick={() => doDelete(p)}>✕</button>
            </div>
          ))}
        </div>
      )}
      {status && <span className="toolbar-status">{status}</span>}
    </div>
  )
}