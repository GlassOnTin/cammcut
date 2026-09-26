import { useEffect, useRef, useState } from 'react'
import Canvas from './components/Canvas'
import CutPanel from './components/CutPanel'
import Inspector from './components/Inspector'
import LayerPanel from './components/LayerPanel'
import PreviewPanel from './components/PreviewPanel'
import ShapesPanel from './components/ShapesPanel'
import TextPanel from './components/TextPanel'
import Toolbar from './components/Toolbar'
import TracePanel from './components/TracePanel'
import TidyPanel from './components/TidyPanel'
import { useStore } from './store'

const TABS = ['Layers', 'Shapes', 'Text', 'Trace', 'Tidy'] as const
type Tab = (typeof TABS)[number]

export default function App() {
  const doc = useStore((s) => s.doc)
  const savedMtime = useStore((s) => s.savedMtime)
  const [tab, setTab] = useState<Tab>('Layers')

  useEffect(() => {
    // open the most recent project on load, if any
    import('./api').then(({ api }) =>
      api
        .listProjects()
        .then((ps) => {
          if (ps.length > 0) useStore.getState().openProject(ps[0].id)
          else useStore.getState().newProject()
        })
        .catch(() => useStore.getState().setStatus('backend unreachable')),
    )
  }, [])

  // autosave 2 s after the last change (skips the initial load, and skips
  // drafts: a document that has never been explicitly saved stays local)
  const loaded = useRef(false)
  useEffect(() => {
    if (!doc) return
    if (!loaded.current) { loaded.current = true; return }
    const t = setTimeout(() => {
      const st = useStore.getState()
      if (st.savedMtime > 0) st.save()
    }, 2000)
    return () => clearTimeout(t)
  }, [doc])

  // warn before closing a draft that has content on it — it exists only in
  // this tab until the first save
  useEffect(() => {
    const hasContent = !!doc && doc.layers.some((l) => l.items.length > 0)
    if (!hasContent || savedMtime > 0) return
    function onBeforeUnload(e: BeforeUnloadEvent) {
      e.preventDefault()
      e.returnValue = '' // required by Chrome
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [doc, savedMtime])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      const st = useStore.getState()
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        e.preventDefault()
        e.shiftKey ? st.redo() : st.undo()
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'y') {
        e.preventDefault()
        st.redo()
      } else if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault()
        st.save()
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
        e.preventDefault()
        st.selectAll()
      } else if (e.key === 'Escape') {
        st.select([])
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        st.deleteSelection()
      } else if (e.key.startsWith('Arrow')) {
        e.preventDefault()
        const step = e.shiftKey ? 10 : 1
        const d: Record<string, [number, number]> = {
          ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step],
        }
        const [dx, dy] = d[e.key] ?? [0, 0]
        st.nudgeSelection(dx, dy)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <div className="app">
      <Toolbar />
      <div className="main">
        <div className="left-col">
          <div className="tabs">
            {TABS.map((t) => (
              <button key={t} className={`tab${tab === t ? ' active' : ''}`}
                onClick={() => setTab(t)}>{t}</button>
            ))}
          </div>
          {tab === 'Layers' && <LayerPanel />}
          {tab === 'Shapes' && <ShapesPanel />}
          {tab === 'Text' && <TextPanel />}
          {tab === 'Trace' && <TracePanel />}
          {tab === 'Tidy' && <TidyPanel />}
        </div>
        <Canvas />
        <div className="right-col">
          <Inspector />
          <PreviewPanel />
          <CutPanel />
        </div>
      </div>
      {!doc && <div className="loading">loading…</div>}
    </div>
  )
}