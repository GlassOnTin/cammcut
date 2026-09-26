import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useStore } from '../store'
import type { Item, Layer } from '../types'
import { itemBox, selectionBox } from '../geom/docBox'
import {
  mul, rotateAbout, rectsIntersect, scaleAbout, translate, unionRects,
  type Mat, type Rect,
} from '../geom/matrix'

export function matrixStr(t: number[]): string {
  return `matrix(${t[0]},${t[1]},${t[2]},${t[3]},${t[4]},${t[5]})`
}

export function screenToDoc(svg: SVGSVGElement, clientX: number, clientY: number): { x: number; y: number } {
  const ctm = svg.getScreenCTM()
  if (!ctm) return { x: 0, y: 0 }
  const p = new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse())
  return { x: p.x, y: p.y }
}

const MIN_SPAN = 2
const MAX_SPAN = 3000

type Handle = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w' | 'rot'
type Pt = { x: number; y: number }

type Drag =
  | { mode: 'pan'; startDoc: Pt; startView: { x: number; y: number } }
  | { mode: 'move'; last: Pt; startBox: Rect; orig: Record<string, Mat> }
  | { mode: 'marquee'; start: Pt; additive: boolean }
  | { mode: 'scale'; handle: Exclude<Handle, 'rot'>; start: Pt; startBox: Rect; orig: Record<string, Mat> }
  | { mode: 'rotate'; start: Pt; center: [number, number]; orig: Record<string, Mat> }

function handlePoints(b: Rect): Record<Exclude<Handle, 'rot'>, [number, number]> {
  const cx = b.x + b.w / 2
  const cy = b.y + b.h / 2
  return {
    nw: [b.x, b.y], n: [cx, b.y], ne: [b.x + b.w, b.y],
    e: [b.x + b.w, cy], se: [b.x + b.w, b.y + b.h],
    s: [cx, b.y + b.h], sw: [b.x, b.y + b.h], w: [b.x, cy],
  }
}

// scale anchor: the handle on the opposite side stays fixed
const ANCHOR: Record<Exclude<Handle, 'rot'>, Exclude<Handle, 'rot'>> = {
  nw: 'se', n: 's', ne: 'sw', e: 'w', se: 'nw', s: 'n', sw: 'ne', w: 'e',
}

export default function Canvas() {
  const doc = useStore((s) => s.doc)
  const view = useStore((s) => s.view)
  const selection = useStore((s) => s.selection)
  const setView = useStore((s) => s.setView)
  const select = useStore((s) => s.select)

  const svgRef = useRef<SVGSVGElement | null>(null)
  const drag = useRef<Drag | null>(null)
  const spaceRef = useRef(false)
  // touch: active pointers + pinch state (two-finger zoom about the midpoint)
  const pointers = useRef<Map<number, Pt>>(new Map())
  const pinch = useRef<{ dist: number } | null>(null)
  const [marquee, setMarquee] = useState<Rect | null>(null)
  const [guides, setGuides] = useState<{ x: number[]; y: number[] } | null>(null)

  // selectable items (visible + unlocked layers), with their doc-space boxes
  const selectable = useMemo(() => {
    const out: { item: Item; box: Rect }[] = []
    if (!doc) return out
    for (const layer of doc.layers) {
      if (!layer.visible || layer.locked) continue
      for (const item of layer.items) {
        const b = itemBox(item)
        if (b) out.push({ item, box: b })
      }
    }
    return out
  }, [doc])

  const selBox = useMemo(() => (doc ? selectionBox(doc, selection) : null), [doc, selection])

  const settings = useStore((s) => s.jobSettings)

  // bbox of everything on visible layers (locked included — compose cuts
  // locked layers too); this is the "content" the origin mode refers to
  const contentBox = useMemo(() => {
    if (!doc) return null
    const boxes: Rect[] = []
    for (const layer of doc.layers) {
      if (!layer.visible) continue
      for (const item of layer.items) {
        const b = itemBox(item)
        if (b) boxes.push(b)
      }
    }
    return unionRects(boxes)
  }, [doc])

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.code === 'Space') spaceRef.current = true
    }
    const up = (e: KeyboardEvent) => {
      if (e.code === 'Space') spaceRef.current = false
    }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
    }
  }, [])

  const onWheel = useCallback(
    (e: React.WheelEvent) => {
      const svg = svgRef.current
      if (!svg || !doc) return
      e.preventDefault()
      const { x: px, y: py } = screenToDoc(svg, e.clientX, e.clientY)
      const factor = Math.pow(1.0015, e.deltaY)
      const w = Math.min(MAX_SPAN, Math.max(MIN_SPAN, view.w * factor))
      const h = w * (view.h / view.w)
      setView({ x: px - (px - view.x) * (w / view.w), y: py - (py - view.y) * (h / view.h), w, h })
    },
    [doc, view, setView],
  )

  const pointerDist = () => {
    const pts = [...pointers.current.values()]
    if (pts.length < 2) return 0
    return Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y)
  }

  // px -> doc units for handle sizes and snap threshold
  const pxToDoc = () => {
    const svg = svgRef.current
    if (!svg) return 1
    return view.w / svg.clientWidth
  }

  const onPointerDown = (e: React.PointerEvent) => {
    const svg = svgRef.current
    if (!svg || !doc) return
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    if (pointers.current.size === 2) {
      // second finger lands: any drag in progress becomes a pinch
      drag.current = null
      setMarquee(null)
      setGuides(null)
      pinch.current = { dist: pointerDist() }
      return
    }
    const target = e.target as Element
    const handle = target.getAttribute?.('data-handle') as Handle | null
    const itemId = target.closest('[data-item-id]')?.getAttribute('data-item-id')
    const originGrab = target.closest?.('[data-origin-marker]')
    const p = screenToDoc(svg, e.clientX, e.clientY)
    try {
      ;(e.currentTarget as Element).setPointerCapture(e.pointerId)
    } catch {
      /* synthetic events carry a pointerId the browser has never seen */
    }

    const st = useStore.getState()

    if (e.button === 1 || spaceRef.current) {
      drag.current = { mode: 'pan', startDoc: p, startView: { x: st.view.x, y: st.view.y } }
      return
    }
    if (e.button !== 0) return

    if (originGrab) {
      // the origin handle moves the whole artwork: the marked corner is the
      // artwork's own (or the artboard's) origin corner, so dragging it
      // repositions everything on unlocked layers
      st.commit()
      st.select(selectable.map((s) => s.item.id))
      const orig: Record<string, Mat> = {}
      for (const s of selectable) orig[s.item.id] = s.item.transform as Mat
      const box = unionRects(selectable.map((s) => s.box))
      if (box && Object.keys(orig).length > 0) {
        drag.current = { mode: 'move', last: p, startBox: box, orig }
      }
      return
    }

    if (handle && selBox) {
      st.commit()
      const orig: Record<string, Mat> = {}
      for (const id of st.selection) {
        const it = findItem(doc, id)
        if (it) orig[id] = it.transform as Mat
      }
      if (handle === 'rot') {
        drag.current = {
          mode: 'rotate', start: p,
          center: [selBox.x + selBox.w / 2, selBox.y + selBox.h / 2], orig,
        }
      } else {
        drag.current = { mode: 'scale', handle, start: p, startBox: selBox, orig }
      }
      return
    }

    if (itemId) {
      const layer = doc.layers.find((l) => l.items.some((it) => it.id === itemId))
      if (layer?.locked) return
      st.select([itemId], e.shiftKey)
      st.commit()
      const orig: Record<string, Mat> = {}
      for (const id of useStore.getState().selection) {
        const it = findItem(doc, id)
        if (it) orig[id] = it.transform as Mat
      }
      const box = selectionBox(doc, useStore.getState().selection)
      if (box) drag.current = { mode: 'move', last: p, startBox: box, orig }
      return
    }

    // empty canvas: marquee (or deselect)
    drag.current = { mode: 'marquee', start: p, additive: e.shiftKey }
    if (!e.shiftKey) select([])
    setMarquee({ x: p.x, y: p.y, w: 0, h: 0 })
  }

  const onPointerMove = (e: React.PointerEvent) => {
    const svg = svgRef.current
    if (!svg || !doc) return
    if (pointers.current.has(e.pointerId)) {
      pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    }
    if (pinch.current && pointers.current.size === 2) {
      const dist = pointerDist()
      if (pinch.current.dist > 1e-6 && dist > 1e-6) {
        // zoom about the midpoint of the two touches, same math as wheel zoom;
        // read the view from the store, not the render closure — two moves can
        // land in the same frame and the closure would go stale
        const v = useStore.getState().view
        const pts = [...pointers.current.values()]
        const mid = { x: (pts[0].x + pts[1].x) / 2, y: (pts[0].y + pts[1].y) / 2 }
        const { x: px, y: py } = screenToDoc(svg, mid.x, mid.y)
        const factor = pinch.current.dist / dist
        const w = Math.min(MAX_SPAN, Math.max(MIN_SPAN, v.w * factor))
        const h = w * (v.h / v.w)
        setView({ x: px - (px - v.x) * (w / v.w), y: py - (py - v.y) * (h / v.h), w, h })
      }
      pinch.current = { dist }
      return
    }
    const d = drag.current
    if (!d) return
    const p = screenToDoc(svg, e.clientX, e.clientY)
    const st = useStore.getState()

    if (d.mode === 'pan') {
      setView({ ...st.view, x: d.startView.x - (p.x - d.startDoc.x), y: d.startView.y - (p.y - d.startDoc.y) })
      return
    }

    if (d.mode === 'marquee') {
      setMarquee({
        x: Math.min(d.start.x, p.x), y: Math.min(d.start.y, p.y),
        w: Math.abs(p.x - d.start.x), h: Math.abs(p.y - d.start.y),
      })
      return
    }

    if (d.mode === 'move') {
      let dx = p.x - d.last.x
      let dy = p.y - d.last.y
      const thr = 6 * pxToDoc()
      const others = selectable.filter((s) => !(s.item.id in d.orig)).map((s) => s.box)
      const snapped = snap(dx, dy, d.startBox, others, doc.artboard.w_mm, doc.artboard.h_mm, thr)
      dx += snapped.dx
      dy += snapped.dy
      setGuides(snapped.guides)
      // rebuild from the original transforms each move (no drift)
      const updates: Record<string, number[]> = {}
      for (const id of Object.keys(d.orig)) updates[id] = mul(translate(dx, dy), d.orig[id])
      st.setItemTransforms(updates)
      return
    }

    if (d.mode === 'scale') {
      const b = d.startBox
      const pts = handlePoints(b)
      const [ax, ay] = pts[ANCHOR[d.handle]]
      let sx = 1
      let sy = 1
      if (d.handle === 'nw' || d.handle === 'ne' || d.handle === 'se' || d.handle === 'sw') {
        const d0 = Math.hypot(d.start.x - ax, d.start.y - ay)
        const d1 = Math.hypot(p.x - ax, p.y - ay)
        const f = d0 > 1e-9 ? d1 / d0 : 1
        sx = sy = Math.min(100, Math.max(0.01, f))
      } else if (d.handle === 'e' || d.handle === 'w') {
        sx = Math.abs(d.start.x - ax) > 1e-9
          ? (p.x - ax) / (d.start.x - ax) : 1
        sx = Math.min(100, Math.max(0.01, sx))
      } else {
        sy = Math.abs(d.start.y - ay) > 1e-9
          ? (p.y - ay) / (d.start.y - ay) : 1
        sy = Math.min(100, Math.max(0.01, sy))
      }
      const m = scaleAbout(sx, sy, ax, ay)
      const updates: Record<string, number[]> = {}
      for (const id of Object.keys(d.orig)) updates[id] = mul(m, d.orig[id])
      st.setItemTransforms(updates)
      return
    }

    if (d.mode === 'rotate') {
      const a0 = Math.atan2(d.start.y - d.center[1], d.start.x - d.center[0])
      let angle = ((Math.atan2(p.y - d.center[1], p.x - d.center[0]) - a0) * 180) / Math.PI
      if (e.shiftKey) angle = Math.round(angle / 15) * 15
      const m = rotateAbout(angle, d.center[0], d.center[1])
      const updates: Record<string, number[]> = {}
      for (const id of Object.keys(d.orig)) updates[id] = mul(m, d.orig[id])
      st.setItemTransforms(updates)
    }
  }

  const onPointerUp = (e?: React.PointerEvent) => {
    if (e) pointers.current.delete(e.pointerId)
    if (pointers.current.size < 2) pinch.current = null
    const svg = svgRef.current
    const d = drag.current
    drag.current = null
    setGuides(null)
    if (!svg || !d) return
    if (d.mode === 'marquee' && marquee) {
      const hits = selectable
        .filter((s) => rectsIntersect(marquee, s.box))
        .map((s) => s.item.id)
      select(hits, d.additive)
      setMarquee(null)
    }
  }

  if (!doc) return <div className="canvas-empty">no project open</div>

  const { w_mm, h_mm } = doc.artboard
  const hs = 7 * pxToDoc() // handle size in doc units

  // the machine origin is the page's bottom-left (HPGL y-up; editor y-down).
  // content mode sends the artwork's own bottom-left there; artboard mode
  // sends the artboard's. No artwork yet -> mark the artboard corner.
  const originPt = settings.origin === 'content' && contentBox
    ? { x: contentBox.x, y: contentBox.y + contentBox.h }
    : { x: 0, y: h_mm }

  return (
    <div className="canvas-wrap">
      <svg
        ref={svgRef}
        className={`canvas${spaceRef.current ? ' panning' : ''}`}
        viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
        preserveAspectRatio="xMidYMid meet"
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <defs>
          <pattern id="grid-minor" width="10" height="10" patternUnits="userSpaceOnUse">
            <path d="M 10 0 L 0 0 0 10" fill="none" style={{ stroke: 'var(--grid-minor)' }} strokeWidth="0.2" />
          </pattern>
          <pattern id="grid-major" width="50" height="50" patternUnits="userSpaceOnUse">
            <rect width="50" height="50" fill="url(#grid-minor)" />
            <path d="M 50 0 L 0 0 0 50" fill="none" style={{ stroke: 'var(--grid-major)' }} strokeWidth="0.4" />
          </pattern>
        </defs>
        <rect x={-w_mm} y={-h_mm} width={w_mm * 3} height={h_mm * 3} fill="url(#grid-major)" />
        <rect x={0} y={0} width={w_mm} height={h_mm} fill="white" stroke="#94a3b8" strokeWidth={0.5} />
        {doc.layers.map((layer: Layer) => (
          <g key={layer.id} style={{ pointerEvents: layer.locked ? 'none' : undefined }}>
            {layer.visible &&
              layer.items.map((item: Item) => (
                <path
                  key={item.id}
                  data-item-id={item.id}
                  d={item.d}
                  transform={matrixStr(item.transform)}
                  fill={selection.includes(item.id) ? '#93c5fd' : '#bae6fd'}
                  fillOpacity={0.45}
                  fillRule={item.fill_rule ?? 'nonzero'}
                  stroke={selection.includes(item.id) ? '#2563eb' : '#0369a1'}
                  strokeWidth={0.4}
                  className="item"
                />
              ))}
          </g>
        ))}

        {/* cut origin marker: corner bracket + label, plus a drag handle on the
            bracket arm. The handle is the only hittable part: dragging it moves
            the whole artwork (the marked corner travels with it). The bracket
            and label pass clicks through — at a bbox corner (empty space for
            stars/circles) or under the sw scale handle, a hittable marker made
            click-drag feel broken. */}
        <g>
          <path
            d={`M ${originPt.x - hs * 2} ${originPt.y} L ${originPt.x} ${originPt.y} L ${originPt.x} ${originPt.y - hs * 2}`}
            fill="none" stroke="#dc2626" strokeWidth={0.8} pointerEvents="none"
          />
          <circle
            data-origin-marker cx={originPt.x - hs * 1.4} cy={originPt.y} r={hs * 0.45}
            fill="#dc2626" style={{ cursor: 'move' }}
          />
          <circle
            data-origin-marker cx={originPt.x - hs * 1.4} cy={originPt.y} r={hs}
            fill="none" pointerEvents="all" style={{ cursor: 'move' }}
          />
          <text
            x={originPt.x + hs * 0.7} y={originPt.y - hs * 0.7}
            fontSize={hs} fill="#dc2626" textAnchor="start" pointerEvents="none"
          >
            cut origin{settings.origin === 'content' ? ' (content)' : ''}
          </text>
        </g>

        {/* snap guides */}
        {guides && (
          <g stroke="#f43f5e" strokeWidth={0.3} pointerEvents="none">
            {guides.x.map((x, i) => (
              <line key={`gx${i}`} x1={x} y1={view.y} x2={x} y2={view.y + view.h} />
            ))}
            {guides.y.map((y, i) => (
              <line key={`gy${i}`} x1={view.x} y1={y} x2={view.x + view.w} y2={y} />
            ))}
          </g>
        )}

        {/* selection overlay */}
        {selBox && (
          <g pointerEvents="none">
            <rect
              x={selBox.x} y={selBox.y} width={selBox.w} height={selBox.h}
              fill="none" stroke="#2563eb" strokeWidth={0.3} strokeDasharray={`${hs / 2} ${hs / 3}`}
              pointerEvents="none"
            />
            {Object.entries(handlePoints(selBox)).map(([k, [hx, hy]]) => (
              <rect
                key={k} data-handle={k} className="handle"
                x={hx - hs / 2} y={hy - hs / 2} width={hs} height={hs}
                pointerEvents="all" style={{ cursor: `${k}-resize` }}
              />
            ))}
            <line
              x1={selBox.x + selBox.w / 2} y1={selBox.y}
              x2={selBox.x + selBox.w / 2} y2={selBox.y - hs * 1.6}
              stroke="#2563eb" strokeWidth={0.3}
            />
            <circle
              data-handle="rot" cx={selBox.x + selBox.w / 2} cy={selBox.y - hs * 1.6}
              r={hs / 2} fill="#fff" stroke="#2563eb" strokeWidth={0.4}
              pointerEvents="all" style={{ cursor: 'grab' }}
            />
          </g>
        )}

        {/* marquee */}
        {marquee && (
          <rect
            x={marquee.x} y={marquee.y} width={marquee.w} height={marquee.h}
            fill="#2563eb22" stroke="#2563eb" strokeWidth={0.3} strokeDasharray="4 3"
            pointerEvents="none"
          />
        )}
      </svg>
    </div>
  )
}

function findItem(doc: NonNullable<ReturnType<typeof useStore.getState>['doc']>, id: string): Item | undefined {
  for (const l of doc.layers) {
    const it = l.items.find((i) => i.id === id)
    if (it) return it
  }
  return undefined
}

type SnapResult = { dx: number; dy: number; guides: { x: number[]; y: number[] } }

/** Snap a moving selection box to artboard edges/centres and other items' edges/centres. */
function snap(
  dx: number, dy: number, box: Rect, others: Rect[],
  artW: number, artH: number, thr: number,
): SnapResult {
  const targetsX = [0, artW / 2, artW]
  const targetsY = [0, artH / 2, artH]
  for (const b of others) {
    targetsX.push(b.x, b.x + b.w / 2, b.x + b.w)
    targetsY.push(b.y, b.y + b.h / 2, b.y + b.h)
  }
  const selX = [box.x + dx, box.x + box.w / 2 + dx, box.x + box.w + dx]
  const selY = [box.y + dy, box.y + box.h / 2 + dy, box.y + box.h + dy]

  const best = (sel: number[], targets: number[]): { d: number; lines: number[] } | null => {
    let bd = Infinity
    let bl = 0
    for (const s of sel) {
      for (const t of targets) {
        const diff = t - s
        if (Math.abs(diff) <= thr && Math.abs(diff) < Math.abs(bd)) {
          bd = diff
          bl = t
        }
      }
    }
    return Number.isFinite(bd) ? { d: bd, lines: [bl] } : null
  }

  const bx = best(selX, targetsX)
  const by = best(selY, targetsY)
  return {
    dx: bx ? bx.d : 0,
    dy: by ? by.d : 0,
    guides: { x: bx ? bx.lines : [], y: by ? by.lines : [] },
  }
}