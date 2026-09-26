import { z } from 'zod'

// Mirrors cammcut/web/schemas.py — keep in sync.
export const Item = z.object({
  id: z.string(),
  kind: z.literal('path').default('path'),
  d: z.string(),
  transform: z.array(z.number()).length(6).default([1, 0, 0, 1, 0, 0]),
  fill_rule: z.enum(['nonzero', 'evenodd']).nullable().optional(),
})
export type Item = z.infer<typeof Item>

export const Layer = z.object({
  id: z.string(),
  name: z.string(),
  visible: z.boolean().default(true),
  locked: z.boolean().default(false),
  items: z.array(Item).default([]),
})
export type Layer = z.infer<typeof Layer>

export const Artboard = z.object({
  w_mm: z.number(),
  h_mm: z.number(),
})

export const Project = z.object({
  id: z.string(),
  name: z.string(),
  version: z.number().default(1),
  artboard: Artboard,
  layers: z.array(Layer).default([]),
})
export type Project = z.infer<typeof Project>

export const JobSettings = z.object({
  speed: z.number().int().min(1).max(30).default(5),
  x_mm: z.number().default(0),
  y_mm: z.number().default(0),
  scale: z.number().positive().default(1),
  mirror: z.boolean().default(false),
  origin: z.enum(['content', 'artboard']).default('content'),
  media_w_mm: z.number().default(584),
  media_h_mm: z.number().default(5000),
  device: z.string().nullable().optional(),
})
export type JobSettings = z.infer<typeof JobSettings>

export const Bounds = z.object({
  min_x: z.number(),
  min_y: z.number(),
  max_x: z.number(),
  max_y: z.number(),
})

export const Violation = z.object({
  axis: z.enum(['x', 'y']),
  detail: z.string(),
})

export const Preview = z.object({
  toolpath_svg: z.string(),
  bounds: Bounds.nullable(),
  violations: z.array(Violation),
  cut_len_mm: z.number(),
  travel_len_mm: z.number(),
  est_seconds: z.number(),
  byte_len: z.number(),
})
export type Preview = z.infer<typeof Preview>

export const ImportResult = z.object({
  svg_id: z.string(),
  width_mm: z.number(),
  height_mm: z.number(),
  warnings: z.array(z.string()),
  items: z.array(Item),
})
export type ImportResult = z.infer<typeof ImportResult>

// Font and text results come straight from the backend (cammcut/web/routers/texttrace.py)
export type FontInfo = { id: string; family: string; style: string; path: string }
export type TextResult = {
  width_mm: number
  height_mm: number
  x_mm: number
  y_mm: number
  warnings: string[]
  items: Item[]
}
export type TraceParams = {
  threshold: number
  invert: boolean
  turdsize: number
  alphamax: number
  opttolerance: number
}
// Mirrors cammcut/web/routers/generate.py — keep in sync.
export type GenerateStatus = {
  configured: boolean
  models: string[]
  default_model: string
  sizes: string[]
}
export type GenerateResult = {
  image_id: string
  w_px: number
  h_px: number
  model: string
}
export type TidyCheck = {
  open_subpaths: number
  duplicate_points: number
  self_crossings: number
  crossing_examples: string[]
}
export type TidyOp = { op: string; params?: Record<string, number> }
export type TidyResult = { items: Item[]; report: { op: string; changed: number }[] }

export const DeviceInfo = z.object({
  path: z.string(),
  vid: z.string(),
  pid: z.string(),
  exists: z.boolean(),
  writable: z.boolean(),
})
export type DeviceInfo = z.infer<typeof DeviceInfo>

export const SystemInfo = z.object({
  version: z.string(),
  python: z.string(),
  data_dir: z.string(),
  potrace: z.boolean(),
  demo: z.boolean().default(false),
  devices: z.array(DeviceInfo),
})
export type SystemInfo = z.infer<typeof SystemInfo>