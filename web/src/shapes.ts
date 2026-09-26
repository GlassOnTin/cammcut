// Parametric shape generators producing path 'd' strings in mm, centred on
// the origin (the caller positions the item).

export type ShapeDef = {
  id: string
  label: string
  params: { key: string; label: string; def: number; min: number; max: number }[]
  make: (p: Record<string, number>) => string
}

const f = (n: number) => (Math.round(n * 1000) / 1000).toString()

function rectD(w: number, h: number): string {
  return `M ${f(-w / 2)} ${f(-h / 2)} H ${f(w / 2)} V ${f(h / 2)} H ${f(-w / 2)} Z`
}

function roundedRectD(w: number, h: number, r: number): string {
  r = Math.min(r, w / 2, h / 2)
  const x = w / 2
  const y = h / 2
  return (
    `M ${f(-x + r)} ${f(-y)} H ${f(x - r)} A ${f(r)} ${f(r)} 0 0 1 ${f(x)} ${f(-y + r)}` +
    ` V ${f(y - r)} A ${f(r)} ${f(r)} 0 0 1 ${f(x - r)} ${f(y)}` +
    ` H ${f(-x + r)} A ${f(r)} ${f(r)} 0 0 1 ${f(-x)} ${f(y - r)}` +
    ` V ${f(-y + r)} A ${f(r)} ${f(r)} 0 0 1 ${f(-x + r)} ${f(-y)} Z`
  )
}

function circleD(r: number): string {
  return `M ${f(r)} 0 A ${f(r)} ${f(r)} 0 0 1 0 ${f(r)} A ${f(r)} ${f(r)} 0 0 1 ${f(-r)} 0 A ${f(r)} ${f(r)} 0 0 1 0 ${f(-r)} A ${f(r)} ${f(r)} 0 0 1 ${f(r)} 0 Z`
}

function polygonD(n: number, r: number): string {
  const pts: string[] = []
  for (let i = 0; i < n; i++) {
    const a = (2 * Math.PI * i) / n - Math.PI / 2
    pts.push(`${f(r * Math.cos(a))} ${f(r * Math.sin(a))}`)
  }
  return `M ${pts.join(' L ')} Z`
}

function starD(n: number, r1: number, r2: number): string {
  const pts: string[] = []
  for (let i = 0; i < 2 * n; i++) {
    const r = i % 2 === 0 ? r1 : r2
    const a = (Math.PI * i) / n - Math.PI / 2
    pts.push(`${f(r * Math.cos(a))} ${f(r * Math.sin(a))}`)
  }
  return `M ${pts.join(' L ')} Z`
}

function heartD(w: number): string {
  // classic cubic heart, unit width scaled to w
  const s = w / 32
  return (
    'M 16 ' + f(28 * s) +
    ' C 10 ' + f(22 * s) + ' 0 ' + f(14 * s) + ' 0 ' + f(7 * s) +
    ' C 0 ' + f(2 * s) + ' 4 0 8 0 C 11 0 14 2 16 5 C 18 2 21 0 24 0' +
    ' C 28 0 32 2 32 ' + f(7 * s) +
    ' C 32 ' + f(14 * s) + ' 22 ' + f(22 * s) + ' 16 ' + f(28 * s) + ' Z'
  )
}

function burstD(n: number, r1: number, r2: number): string {
  return starD(n, r1, r2)
}

function arrowD(w: number, h: number, tail: number): string {
  const x = w / 2
  const y = h / 2
  const tx = x * tail
  return (
    `M ${f(-x)} ${f(-y * tail)} L ${f(tx)} ${f(-y * tail)} L ${f(tx)} ${f(-y)}` +
    ` L ${f(x)} 0 L ${f(tx)} ${f(y)} L ${f(tx)} ${f(y * tail)}` +
    ` L ${f(-x)} ${f(y * tail)} Z`
  )
}

export const SHAPES: ShapeDef[] = [
  {
    id: 'rect', label: 'rectangle',
    params: [
      { key: 'w', label: 'width', def: 40, min: 1, max: 500 },
      { key: 'h', label: 'height', def: 30, min: 1, max: 500 },
    ],
    make: (p) => rectD(p.w, p.h),
  },
  {
    id: 'rounded', label: 'rounded rect',
    params: [
      { key: 'w', label: 'width', def: 40, min: 1, max: 500 },
      { key: 'h', label: 'height', def: 30, min: 1, max: 500 },
      { key: 'r', label: 'corner', def: 6, min: 0, max: 250 },
    ],
    make: (p) => roundedRectD(p.w, p.h, p.r),
  },
  {
    id: 'circle', label: 'circle',
    params: [{ key: 'r', label: 'radius', def: 15, min: 0.5, max: 250 }],
    make: (p) => circleD(p.r),
  },
  {
    id: 'polygon', label: 'polygon',
    params: [
      { key: 'n', label: 'sides', def: 6, min: 3, max: 24 },
      { key: 'r', label: 'radius', def: 15, min: 0.5, max: 250 },
    ],
    make: (p) => polygonD(Math.round(p.n), p.r),
  },
  {
    id: 'star', label: 'star',
    params: [
      { key: 'n', label: 'points', def: 5, min: 3, max: 24 },
      { key: 'r1', label: 'outer r', def: 20, min: 1, max: 250 },
      { key: 'r2', label: 'inner r', def: 8, min: 0.2, max: 250 },
    ],
    make: (p) => starD(Math.round(p.n), p.r1, p.r2),
  },
  {
    id: 'burst', label: 'burst',
    params: [
      { key: 'n', label: 'spikes', def: 12, min: 3, max: 36 },
      { key: 'r1', label: 'outer r', def: 20, min: 1, max: 250 },
      { key: 'r2', label: 'inner r', def: 14, min: 0.2, max: 250 },
    ],
    make: (p) => burstD(Math.round(p.n), p.r1, p.r2),
  },
  {
    id: 'heart', label: 'heart',
    params: [{ key: 'w', label: 'width', def: 30, min: 5, max: 300 }],
    make: (p) => heartD(p.w),
  },
  {
    id: 'arrow', label: 'arrow',
    params: [
      { key: 'w', label: 'length', def: 50, min: 5, max: 500 },
      { key: 'h', label: 'head h', def: 24, min: 2, max: 300 },
      { key: 'tail', label: 'tail %', def: 0.4, min: 0.05, max: 0.95 },
    ],
    make: (p) => arrowD(p.w, p.h, p.tail),
  },
]