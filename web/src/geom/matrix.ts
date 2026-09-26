// Affine matrix helpers (SVG column-major [a,b,c,d,e,f], same as transform="matrix(...)").
// All matrices operate in document (mm) space, y-down like SVG.

export type Mat = [number, number, number, number, number, number]
export type Rect = { x: number; y: number; w: number; h: number }

export const IDENT: Mat = [1, 0, 0, 1, 0, 0]

/** m * n — apply n first, then m. */
export function mul(m: Mat, n: Mat): Mat {
  return [
    m[0] * n[0] + m[2] * n[1],
    m[1] * n[0] + m[3] * n[1],
    m[0] * n[2] + m[2] * n[3],
    m[1] * n[2] + m[3] * n[3],
    m[0] * n[4] + m[2] * n[5] + m[4],
    m[1] * n[4] + m[3] * n[5] + m[5],
  ]
}

export function apply(m: Mat, x: number, y: number): [number, number] {
  return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]]
}

export function translate(tx: number, ty: number): Mat {
  return [1, 0, 0, 1, tx, ty]
}

export function scaleAbout(sx: number, sy: number, cx: number, cy: number): Mat {
  return mul(translate(cx, cy), mul([sx, 0, 0, sy, 0, 0], translate(-cx, -cy)))
}

export function rotateAbout(deg: number, cx: number, cy: number): Mat {
  const r = (deg * Math.PI) / 180
  const cos = Math.cos(r)
  const sin = Math.sin(r)
  return mul(translate(cx, cy), mul([cos, sin, -sin, cos, 0, 0], translate(-cx, -cy)))
}

export function rectCorners(b: Rect, m: Mat): [number, number][] {
  return [
    apply(m, b.x, b.y),
    apply(m, b.x + b.w, b.y),
    apply(m, b.x + b.w, b.y + b.h),
    apply(m, b.x, b.y + b.h),
  ]
}

export function unionPts(pts: [number, number][]): Rect {
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const [x, y] of pts) {
    if (x < minX) minX = x
    if (y < minY) minY = y
    if (x > maxX) maxX = x
    if (y > maxY) maxY = y
  }
  return { x: minX, y: minY, w: maxX - minX, h: maxY - minY }
}

export function rectsIntersect(a: Rect, b: Rect): boolean {
  return a.x <= b.x + b.w && a.x + a.w >= b.x && a.y <= b.y + b.h && a.y + a.h >= b.y
}

export function unionRects(boxes: Rect[]): Rect | null {
  if (boxes.length === 0) return null
  const x = Math.min(...boxes.map((b) => b.x))
  const y = Math.min(...boxes.map((b) => b.y))
  return {
    x,
    y,
    w: Math.max(...boxes.map((b) => b.x + b.w)) - x,
    h: Math.max(...boxes.map((b) => b.y + b.h)) - y,
  }
}