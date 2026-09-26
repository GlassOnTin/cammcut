import { create } from 'zustand'
import { api } from './api'
import type { Item, JobSettings, Project } from './types'
import { Artboard, JobSettings as JobSettingsSchema, Project as ProjectSchema } from './types'
import { type Mat, mul } from './geom/matrix'

export type View = { x: number; y: number; w: number; h: number }

export type StoreState = {
  doc: Project | null
  selection: string[]
  view: View
  past: Project[]
  future: Project[]
  status: string
  savedMtime: number
  jobSettings: JobSettings
  setJobSettings: (s: Partial<JobSettings>) => void
  // document actions
  newProject: (name?: string) => Promise<void>
  openProject: (id: string) => Promise<void>
  save: () => Promise<void>
  renameProject: (id: string, name: string) => Promise<void>
  deleteProject: (id: string) => Promise<void>
  setArtboard: (w: number, h: number) => void
  setDoc: (doc: Project) => void
  addLayer: (name: string) => void
  addLayerWithItems: (name: string, items: Item[]) => void
  insertItems: (layerName: string, items: Item[]) => void
  deleteLayer: (id: string) => void
  renameLayer: (id: string, name: string) => void
  toggleLayerVisible: (id: string) => void
  toggleLayerLocked: (id: string) => void
  moveLayer: (id: string, dir: -1 | 1) => void
  // item actions
  select: (ids: string[], additive?: boolean) => void
  setItemTransform: (itemId: string, t: number[], commit?: boolean) => void
  setItemTransforms: (updates: Record<string, number[]>, commit?: boolean) => void
  translateSelection: (dx: number, dy: number, commit?: boolean) => void
  transformSelection: (m: number[], commit?: boolean) => void
  deleteSelection: () => void
  duplicateSelection: () => void
  nudgeSelection: (dx: number, dy: number) => void
  selectAll: () => void
  // history
  commit: () => void
  undo: () => void
  redo: () => void
  // view
  setView: (v: View) => void
  fitView: (padding?: number) => void
  setStatus: (s: string) => void
}

export function uid(): string {
  return Math.random().toString(36).slice(2, 10)
}

const clone = (p: Project): Project => ProjectSchema.parse(structuredClone(p))

export const useStore = create<StoreState>((set, get) => ({
  doc: null,
  selection: [],
  view: { x: 0, y: 0, w: 584, h: 300 },
  past: [],
  future: [],
  status: '',
  savedMtime: 0,
  jobSettings: JobSettingsSchema.parse({}),

  setJobSettings: (s) => set({ jobSettings: { ...get().jobSettings, ...s } }),

  // a new document is a local draft (savedMtime 0): nothing is written to
  // the server until the first explicit save, so experimenting never
  // litters the projects list with "untitled" entries
  newProject: async (name = 'untitled') => {
    const project = ProjectSchema.parse({ id: uid(), name, artboard: { w_mm: 584, h_mm: 300 } })
    set({ doc: project, savedMtime: 0, selection: [], past: [], future: [] })
    get().fitView()
  },

  openProject: async (id) => {
    const { project, mtime } = await api.getProject(id)
    set({ doc: project, savedMtime: mtime, selection: [], past: [], future: [] })
    get().fitView()
  },

  save: async () => {
    const doc = get().doc
    if (!doc) return
    try {
      // a draft (savedMtime 0) saves with base_mtime=0: the server creates
      // the project, and a stray id collision is a 409, not an overwrite
      const { mtime } = await api.saveProject(doc, get().savedMtime || 0)
      set({ savedMtime: mtime, status: `saved ${new Date().toLocaleTimeString()}` })
    } catch (e) {
      // conflict (saved elsewhere) or network failure: keep the local doc,
      // surface it — never silently overwrite or crash the autosave
      set({ status: `save failed: ${(e as Error).message}` })
    }
  },

  renameProject: async (id, name) => {
    const trimmed = name.trim()
    if (!trimmed) return
    const doc = get().doc
    if (doc && doc.id === id) {
      // the open document: rename locally. Only an already-saved project
      // is written back — naming a draft must not create it server-side
      set({ doc: { ...doc, name: trimmed } })
      if (get().savedMtime > 0) await get().save()
    } else {
      // a closed project: the API does a conflict-checked read-modify-write
      await api.renameProject(id, trimmed)
      set({ status: `renamed to ${trimmed}` })
    }
  },

  deleteProject: async (id) => {
    // the open draft is not on the server; nothing to delete — start fresh
    if (get().doc?.id === id && get().savedMtime === 0) {
      await get().newProject()
      return
    }
    await api.deleteProject(id)
    // if that was the open document, its saves would 404 — start a fresh one
    if (get().doc?.id === id) await get().newProject()
  },

  setArtboard: (w, h) => {
    get().commit()
    const { doc } = get()
    if (!doc) return
    set({ doc: { ...doc, artboard: Artboard.parse({ w_mm: w, h_mm: h }) } })
  },

  setDoc: (doc) => set({ doc }),

  addLayer: (name) => {
    get().commit()
    const { doc } = get()
    if (!doc) return
    set({
      doc: {
        ...doc,
        layers: [...doc.layers, { id: uid(), name, visible: true, locked: false, items: [] }],
      },
    })
  },

  addLayerWithItems: (name, items) => {
    get().commit()
    const { doc } = get()
    if (!doc) return
    set({
      doc: {
        ...doc,
        layers: [...doc.layers, { id: uid(), name, visible: true, locked: false, items }],
      },
    })
  },

  // Append items to the named layer, creating it if missing or locked.
  insertItems: (layerName, items) => {
    get().commit()
    const { doc } = get()
    if (!doc) return
    const existing = doc.layers.find((l) => l.name === layerName && !l.locked)
    if (existing) {
      set({
        doc: {
          ...doc,
          layers: doc.layers.map((l) =>
            l.id === existing.id ? { ...l, items: [...l.items, ...items] } : l),
        },
      })
    } else {
      set({
        doc: {
          ...doc,
          layers: [...doc.layers, { id: uid(), name: layerName, visible: true, locked: false, items }],
        },
      })
    }
    set({ selection: items.map((it) => it.id) })
  },

  deleteLayer: (id) => {
    get().commit()
    const { doc } = get()
    if (!doc) return
    set({
      doc: { ...doc, layers: doc.layers.filter((l) => l.id !== id) },
      selection: [],
    })
  },

  renameLayer: (id, name) => {
    get().commit()
    const { doc } = get()
    if (!doc) return
    set({ doc: { ...doc, layers: doc.layers.map((l) => (l.id === id ? { ...l, name } : l)) } })
  },

  toggleLayerVisible: (id) => {
    get().commit()
    const { doc } = get()
    if (!doc) return
    set({
      doc: { ...doc, layers: doc.layers.map((l) => (l.id === id ? { ...l, visible: !l.visible } : l)) },
    })
  },

  toggleLayerLocked: (id) => {
    get().commit()
    const { doc } = get()
    if (!doc) return
    set({
      doc: { ...doc, layers: doc.layers.map((l) => (l.id === id ? { ...l, locked: !l.locked } : l)) },
    })
  },

  moveLayer: (id, dir) => {
    get().commit()
    const { doc } = get()
    if (!doc) return
    const layers = [...doc.layers]
    const i = layers.findIndex((l) => l.id === id)
    const j = i + dir
    if (i < 0 || j < 0 || j >= layers.length) return
    ;[layers[i], layers[j]] = [layers[j], layers[i]]
    set({ doc: { ...doc, layers } })
  },

  select: (ids, additive = false) => {
    set({ selection: additive ? [...new Set([...get().selection, ...ids])] : ids })
  },

  setItemTransform: (itemId, t, commit = false) => {
    if (commit) get().commit()
    const { doc } = get()
    if (!doc) return
    set({
      doc: {
        ...doc,
        layers: doc.layers.map((l) => ({
          ...l,
          items: l.items.map((it) => (it.id === itemId ? { ...it, transform: t } : it)),
        })),
      },
    })
  },

  setItemTransforms: (updates, commit = false) => {
    if (commit) get().commit()
    const { doc } = get()
    if (!doc) return
    set({
      doc: {
        ...doc,
        layers: doc.layers.map((l) => ({
          ...l,
          items: l.items.map((it) =>
            updates[it.id] ? { ...it, transform: updates[it.id] } : it),
        })),
      },
    })
  },

  translateSelection: (dx, dy, commit = false) => {
    if (commit) get().commit()
    const { doc, selection } = get()
    if (!doc || selection.length === 0) return
    const sel = new Set(selection)
    const moved = (it: Item): Item => {
      if (!sel.has(it.id)) return it
      const [a, b, c, d, e, f] = it.transform
      // translate in the parent (mm) space: pre-multiply
      return { ...it, transform: [a, b, c, d, e + dx * a + dy * c, f + dx * b + dy * d] }
    }
    set({
      doc: {
        ...doc,
        layers: doc.layers.map((l) => ({ ...l, items: l.items.map(moved) })),
      },
    })
  },

  // m is expressed in document (mm) space: each selected item's transform
  // becomes m * t (m applied after the item's own transform).
  transformSelection: (m, commit = false) => {
    if (commit) get().commit()
    const { doc, selection } = get()
    if (!doc || selection.length === 0) return
    const sel = new Set(selection)
    const mapped = (it: Item): Item =>
      sel.has(it.id)
        ? { ...it, transform: mul(m as Mat, it.transform as Mat) }
        : it
    set({
      doc: {
        ...doc,
        layers: doc.layers.map((l) => ({ ...l, items: l.items.map(mapped) })),
      },
    })
  },

  selectAll: () => {
    const { doc } = get()
    if (!doc) return
    set({
      selection: doc.layers
        .filter((l) => l.visible && !l.locked)
        .flatMap((l) => l.items.map((it) => it.id)),
    })
  },

  deleteSelection: () => {
    get().commit()
    const { doc, selection } = get()
    if (!doc || selection.length === 0) return
    const sel = new Set(selection)
    set({
      doc: { ...doc, layers: doc.layers.map((l) => ({ ...l, items: l.items.filter((it) => !sel.has(it.id)) })) },
      selection: [],
    })
  },

  duplicateSelection: () => {
    const { doc, selection } = get()
    if (!doc || selection.length === 0) return
    get().commit()
    const sel = new Set(selection)
    const idMap = new Map<string, string>()
    for (const id of selection) idMap.set(id, uid())
    set({
      doc: {
        ...doc,
        layers: doc.layers.map((l) => {
          if (!l.items.some((it) => sel.has(it.id))) return l
          const copies = l.items
            .filter((it) => sel.has(it.id))
            .map((it) => ({
              ...it,
              id: idMap.get(it.id)!,
              // offset copies by 5 mm so they are visibly separate
              transform: [
                it.transform[0], it.transform[1], it.transform[2], it.transform[3],
                it.transform[4] + 5, it.transform[5] + 5,
              ],
            }))
          return { ...l, items: [...l.items, ...copies] }
        }),
      },
      selection: [...idMap.values()],
    })
  },

  nudgeSelection: (dx, dy) => {
    get().commit()
    get().translateSelection(dx, dy)
  },

  commit: () => {
    const { doc, past } = get()
    if (!doc) return
    set({ past: [...past.slice(-49), clone(doc)], future: [] })
  },

  undo: () => {
    const { past, future, doc } = get()
    if (!doc || past.length === 0) return
    const prev = past[past.length - 1]
    set({ doc: prev, past: past.slice(0, -1), future: [...future, clone(doc)], selection: [] })
  },

  redo: () => {
    const { past, future, doc } = get()
    if (!doc || future.length === 0) return
    const next = future[future.length - 1]
    set({ doc: next, future: future.slice(0, -1), past: [...past, clone(doc)], selection: [] })
  },

  setView: (v) => set({ view: v }),

  fitView: (padding = 10) => {
    const { doc } = get()
    if (!doc) return
    const { w_mm, h_mm } = doc.artboard
    set({ view: { x: -padding, y: -padding, w: w_mm + 2 * padding, h: h_mm + 2 * padding } })
  },

  setStatus: (s) => set({ status: s }),
}))
// dev/debug handle (harmless in prod)
if (typeof window !== 'undefined') {
  ;(window as unknown as { __cammcutStore?: typeof useStore }).__cammcutStore = useStore
}
