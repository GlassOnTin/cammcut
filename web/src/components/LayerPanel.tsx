import { useStore } from '../store'

export default function LayerPanel() {
  const doc = useStore((s) => s.doc)
  const selection = useStore((s) => s.selection)
  const addLayer = useStore((s) => s.addLayer)
  const deleteLayer = useStore((s) => s.deleteLayer)
  const renameLayer = useStore((s) => s.renameLayer)
  const toggleLayerVisible = useStore((s) => s.toggleLayerVisible)
  const toggleLayerLocked = useStore((s) => s.toggleLayerLocked)
  const moveLayer = useStore((s) => s.moveLayer)

  if (!doc) return null
  // render top-most first in the panel
  const layers = [...doc.layers].reverse()

  return (
    <div className="panel">
      <div className="panel-title">
        Layers
        <button onClick={() => addLayer(`layer ${doc.layers.length + 1}`)}>+</button>
      </div>
      <div className="layer-list">
        {layers.map((l) => (
          <div key={l.id} className="layer-row">
            <button
              title={l.visible ? 'hide' : 'show'}
              className={l.visible ? 'on' : 'off'}
              onClick={() => toggleLayerVisible(l.id)}
            >
              {l.visible ? '◉' : '○'}
            </button>
            <button title={l.locked ? 'unlock' : 'lock'} className={l.locked ? 'on' : 'off'} onClick={() => toggleLayerLocked(l.id)}>
              {l.locked ? '🔒' : '🔓'}
            </button>
            <input
              className="layer-name"
              value={l.name}
              onChange={(e) => renameLayer(l.id, e.target.value)}
            />
            <span className="layer-count">{l.items.length}</span>
            <button title="move up" onClick={() => moveLayer(l.id, 1)}>▲</button>
            <button title="move down" onClick={() => moveLayer(l.id, -1)}>▼</button>
            <button title="delete layer" onClick={() => deleteLayer(l.id)}>✕</button>
          </div>
        ))}
        {layers.length === 0 && <div className="hint">empty document</div>}
      </div>
      {selection.length > 0 && (
        <div className="hint">{selection.length} selected</div>
      )}
    </div>
  )
}