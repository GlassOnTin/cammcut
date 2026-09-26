// Path 'd' parsing and bounding box, without the DOM.
//
// Exact for lines; Bézier bounds use their control-point hull (a slight
// over-estimate); arcs are exact via the centre parameterisation.

import type { Rect } from './matrix'
import { unionPts } from './matrix'

type Pt = { x: number; y: number }

const CMD = /^[MmLlHhVvCcSsQqTtAaZz]$/
const TOKEN = /[MmLlHhVvCcSsQqTtAaZz]|[+-]?(?:\d*\.\d+|\d+\.?)(?:[eE][+-]?\d+)?/g

class Reader {
  toks: string[]
  i = 0
  constructor(d: string) {
    this.toks = d.match(TOKEN) ?? []
  }
  cmd(): string | null {
    const t = this.toks[this.i]
    return t && CMD.test(t) ? t : null
  }
  take(): string | undefined {
    return this.toks[this.i++]
  }
  num(): number {
    return parseFloat(this.toks[this.i++])
  }
}

// Endpoints -> centre parameterisation; returns {cx, cy, th1, dth} (radians).
function arcCentre(rx: number, ry: number, rot: number, large: number, sweep: number,
                   x1: number, y1: number, x2: number, y2: number) {
  const phi = (rot * Math.PI) / 180
  const cosP = Math.cos(phi)
  const sinP = Math.sin(phi)
  const dx = (x1 - x2) / 2
  const dy = (y1 - y2) / 2
  const x1p = cosP * dx + sinP * dy
  const y1p = -sinP * dx + cosP * dy
  let rxa = Math.abs(rx)
  let rya = Math.abs(ry)
  const lambda = (x1p * x1p) / (rxa * rxa) + (y1p * y1p) / (rya * rya)
  if (lambda > 1) {
    const s = Math.sqrt(lambda)
    rxa *= s
    rya *= s
  }
  const sign = large !== sweep ? 1 : -1
  const num = rxa * rxa * rya * rya - rxa * rxa * y1p * y1p - rya * rya * x1p * x1p
  const denom = rxa * rxa * y1p * y1p + rya * rya * x1p * x1p
  const c = sign * Math.sqrt(Math.max(0, num / Math.max(denom, 1e-12)))
  const cxp = (c * rxa * y1p) / rya
  const cyp = (-c * rya * x1p) / rxa
  const cx = cosP * cxp - sinP * cyp + (x1 + x2) / 2
  const cy = sinP * cxp + cosP * cyp + (y1 + y2) / 2
  const ux = (x1p - cxp) / rxa
  const uy = (y1p - cyp) / rya
  const vx = (-x1p - cxp) / rxa
  const vy = (-y1p - cyp) / rya
  const th1 = Math.atan2(uy, ux)
  let dth = Math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
  if (!sweep && dth > 0) dth -= 2 * Math.PI
  if (sweep && dth < 0) dth += 2 * Math.PI
  return { cx, cy, rxa, rya, phi, th1, dth }
}

function arcPoints(rx: number, ry: number, rot: number, large: number, sweep: number,
                   x1: number, y1: number, x2: number, y2: number): Pt[] {
  const { cx, cy, rxa, rya, phi, th1, dth } = arcCentre(rx, ry, rot, large, sweep, x1, y1, x2, y2)
  const out: Pt[] = [{ x: x1, y: y1 }, { x: x2, y: y2 }]
  for (let k = 0; k < 4; k++) {
    const th = (k * Math.PI) / 2
    // distance from th1 to th, measured in the sweep direction
    let t = ((th - th1) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI)
    if (dth >= 0 ? t <= dth : 2 * Math.PI + dth <= t) {
      // inside the swept range
    } else {
      continue
    }
    const cosP = Math.cos(phi)
    const sinP = Math.sin(phi)
    const px = cosP * rxa * Math.cos(th) - sinP * rya * Math.sin(th) + cx
    const py = sinP * rxa * Math.cos(th) + cosP * rya * Math.sin(th) + cy
    out.push({ x: px, y: py })
  }
  return out
}

function cubicExtremes(p0: Pt, p1: Pt, p2: Pt, p3: Pt): Pt[] {
  const out: Pt[] = []
  for (const axis of ['x', 'y'] as const) {
    const a = 3 * (p1[axis] - p0[axis])
    const b = 3 * (p2[axis] - 2 * p1[axis] + p0[axis])
    const c = p3[axis] - 3 * p2[axis] + 3 * p1[axis] - p0[axis]
    // B(t) = c t^3 + b t^2 + a t + p0, so B'(t) = 3c t^2 + 2b t + a
    for (const t of realRoots(3 * c, 2 * b, a)) {
      if (t <= 0 || t >= 1) continue
      const mt = 1 - t
      out.push({
        x: mt * mt * mt * p0.x + 3 * mt * mt * t * p1.x + 3 * mt * t * t * p2.x + t * t * t * p3.x,
        y: mt * mt * mt * p0.y + 3 * mt * mt * t * p1.y + 3 * mt * t * t * p2.y + t * t * t * p3.y,
      })
    }
  }
  return out
}

// roots of a t^2 + b t + c = 0
function realRoots(a: number, b: number, c: number): number[] {
  if (Math.abs(a) < 1e-12) {
    if (Math.abs(b) < 1e-12) return []
    return [-c / b]
  }
  const disc = b * b - 4 * a * c
  if (disc < 0) return []
  const s = Math.sqrt(disc)
  return [(-b + s) / (2 * a), (-b - s) / (2 * a)]
}

function quadExtremes(p0: Pt, p1: Pt, p2: Pt): Pt[] {
  const out: Pt[] = []
  for (const axis of ['x', 'y'] as const) {
    const denom = p0[axis] - 2 * p1[axis] + p2[axis]
    if (Math.abs(denom) < 1e-12) continue
    const t = (p0[axis] - p1[axis]) / denom
    if (t <= 0 || t >= 1) continue
    const mt = 1 - t
    out.push({
      x: mt * mt * p0.x + 2 * mt * t * p1.x + t * t * p2.x,
      y: mt * mt * p0.y + 2 * mt * t * p1.y + t * t * p2.y,
    })
  }
  return out
}

/** Bounding box of a path in its own (untransformed) coordinate space, or null if empty. */
export function pathBBox(d: string): Rect | null {
  const r = new Reader(d)
  if (r.toks.length === 0) return null
  let cur: Pt = { x: 0, y: 0 }
  let startPt: Pt = { x: 0, y: 0 }
  let lastC: Pt | null = null
  let lastQ: Pt | null = null
  const pts: Pt[] = []
  const add = (p: Pt) => pts.push(p)

  let cmd: string | null = null
  for (;;) {
    const peek = r.cmd()
    if (peek) {
      cmd = peek
      r.take()
      if (cmd === 'Z' || cmd === 'z') {
        cur = { ...startPt }
        cmd = null
        continue
      }
    } else if (!cmd) {
      break
    }
    switch (cmd) {
      case 'M':
      case 'm': {
        const rel: boolean = cmd === 'm'
        const x = r.num()
        const y = r.num()
        if (Number.isNaN(x) || Number.isNaN(y)) return pts.length ? bboxOf(pts) : null
        cur = { x: rel ? cur.x + x : x, y: rel ? cur.y + y : y }
        startPt = { ...cur }
        add(cur)
        cmd = rel ? 'l' : 'L' // implicit linetos follow
        break
      }
      case 'L':
      case 'l': {
        const rel = cmd === 'l'
        const x = r.num()
        const y = r.num()
        if (Number.isNaN(x) || Number.isNaN(y)) return pts.length ? bboxOf(pts) : null
        cur = { x: rel ? cur.x + x : x, y: rel ? cur.y + y : y }
        add(cur)
        break
      }
      case 'H':
      case 'h': {
        const rel = cmd === 'h'
        const x = r.num()
        if (Number.isNaN(x)) return pts.length ? bboxOf(pts) : null
        cur = { x: rel ? cur.x + x : x, y: cur.y }
        add(cur)
        break
      }
      case 'V':
      case 'v': {
        const rel = cmd === 'v'
        const y = r.num()
        if (Number.isNaN(y)) return pts.length ? bboxOf(pts) : null
        cur = { x: cur.x, y: rel ? cur.y + y : y }
        add(cur)
        break
      }
      case 'C':
      case 'c': {
        const rel = cmd === 'c'
        const p1 = { x: r.num(), y: r.num() }
        const p2 = { x: r.num(), y: r.num() }
        const p3 = { x: r.num(), y: r.num() }
        if ([p1, p2, p3].some((p) => Number.isNaN(p.x) || Number.isNaN(p.y)))
          return pts.length ? bboxOf(pts) : null
        if (rel) {
          p1.x += cur.x
          p1.y += cur.y
          p2.x += cur.x
          p2.y += cur.y
          p3.x += cur.x
          p3.y += cur.y
        }
        add(cur)
        for (const p of cubicExtremes(cur, p1, p2, p3)) add(p)
        add(p3)
        cur = p3
        lastC = p2
        lastQ = null
        break
      }
      case 'S':
      case 's': {
        const rel = cmd === 's'
        const p2 = { x: r.num(), y: r.num() }
        const p3 = { x: r.num(), y: r.num() }
        if ([p2, p3].some((p) => Number.isNaN(p.x) || Number.isNaN(p.y)))
          return pts.length ? bboxOf(pts) : null
        if (rel) {
          p2.x += cur.x
          p2.y += cur.y
          p3.x += cur.x
          p3.y += cur.y
        }
        const p1 = lastC ? { x: 2 * cur.x - lastC.x, y: 2 * cur.y - lastC.y } : cur
        add(cur)
        for (const p of cubicExtremes(cur, p1, p2, p3)) add(p)
        add(p3)
        cur = p3
        lastC = p2
        lastQ = null
        break
      }
      case 'Q':
      case 'q': {
        const rel = cmd === 'q'
        const p1 = { x: r.num(), y: r.num() }
        const p2 = { x: r.num(), y: r.num() }
        if ([p1, p2].some((p) => Number.isNaN(p.x) || Number.isNaN(p.y)))
          return pts.length ? bboxOf(pts) : null
        if (rel) {
          p1.x += cur.x
          p1.y += cur.y
          p2.x += cur.x
          p2.y += cur.y
        }
        add(cur)
        for (const p of quadExtremes(cur, p1, p2)) add(p)
        add(p2)
        cur = p2
        lastQ = p1
        lastC = null
        break
      }
      case 'T':
      case 't': {
        const rel = cmd === 't'
        const p2 = { x: r.num(), y: r.num() }
        if (Number.isNaN(p2.x) || Number.isNaN(p2.y)) return pts.length ? bboxOf(pts) : null
        if (rel) {
          p2.x += cur.x
          p2.y += cur.y
        }
        const p1: Pt = lastQ ? { x: 2 * cur.x - lastQ.x, y: 2 * cur.y - lastQ.y } : cur
        add(cur)
        for (const p of quadExtremes(cur, p1, p2)) add(p)
        add(p2)
        cur = p2
        lastQ = p1
        lastC = null
        break
      }
      case 'A':
      case 'a': {
        const rel = cmd === 'a'
        const rx = r.num()
        const ry = r.num()
        const rot = r.num()
        const large = r.num()
        const sweep = r.num()
        const x = r.num()
        const y = r.num()
        if ([rx, ry, rot, large, sweep, x, y].some((v) => Number.isNaN(v)))
          return pts.length ? bboxOf(pts) : null
        const ax = rel ? cur.x + x : x
        const ay = rel ? cur.y + y : y
        for (const p of arcPoints(rx, ry, rot, large, sweep, cur.x, cur.y, ax, ay)) add(p)
        cur = { x: ax, y: ay }
        lastC = null
        lastQ = null
        break
      }
      default:
        return pts.length ? bboxOf(pts) : null
    }
  }
  return pts.length ? bboxOf(pts) : null
}

function bboxOf(pts: Pt[]): Rect {
  return unionPts(pts.map((p) => [p.x, p.y] as [number, number]))
}

const bboxCache = new Map<string, Rect | null>()

/** Memoised pathBBox keyed on the d string. */
export function cachedPathBBox(d: string): Rect | null {
  if (!bboxCache.has(d)) {
    if (bboxCache.size > 5000) bboxCache.clear()
    bboxCache.set(d, pathBBox(d))
  }
  return bboxCache.get(d) ?? null
}