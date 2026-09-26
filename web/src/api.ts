import type { FontInfo, GenerateResult, GenerateStatus, ImportResult, Item, JobSettings, Preview, Project, SystemInfo, TextResult, TidyCheck, TidyOp, TidyResult, TraceParams } from './types'

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* keep statusText */
    }
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  systemInfo: () => fetch('/api/system/info').then(jsonOrThrow<SystemInfo>),

  createProject: (name: string) =>
    fetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }).then(jsonOrThrow<{ project: Project; mtime: number }>),

  listProjects: () => fetch('/api/projects').then(jsonOrThrow<{ id: string; name: string; mtime: number }[]>),

  getProject: (id: string) => fetch(`/api/projects/${id}`).then(jsonOrThrow<{ project: Project; mtime: number }>),

  saveProject: (project: Project, baseMtime?: number) =>
    // baseMtime 0 is meaningful (a draft's first save) — test undefined, not truthiness
    fetch(`/api/projects/${project.id}${baseMtime === undefined ? '' : `?base_mtime=${baseMtime}`}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(project),
    }).then(jsonOrThrow<{ saved: boolean; mtime: number }>),

  deleteProject: (id: string) =>
    fetch(`/api/projects/${id}`, { method: 'DELETE' }).then(jsonOrThrow<{ deleted: boolean }>),

  renameProject: (id: string, name: string) =>
    // conflict-checked read-modify-write: reload, set the name, save
    api.getProject(id).then(({ project, mtime }) =>
      api.saveProject({ ...project, name }, mtime).then(() => undefined)),

  importSvg: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return fetch('/api/import/svg', { method: 'POST', body: form }).then(jsonOrThrow<ImportResult>)
  },

  listFonts: () => fetch('/api/fonts').then(jsonOrThrow<FontInfo[]>),

  textToPath: (text: string, fontId: string, sizeMm: number, trackingMm: number) =>
    fetch('/api/text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, font_id: fontId, size_mm: sizeMm, tracking_mm: trackingMm }),
    }).then(jsonOrThrow<TextResult>),

  traceImage: (file: File, p: TraceParams) => {
    const form = new FormData()
    form.append('file', file)
    const qs = new URLSearchParams({
      threshold: String(p.threshold),
      invert: String(p.invert),
      turdsize: String(p.turdsize),
      alphamax: String(p.alphamax),
      opttolerance: String(p.opttolerance),
    })
    return fetch(`/api/trace?${qs}`, { method: 'POST', body: form }).then(jsonOrThrow<ImportResult>)
  },

  generateStatus: () => fetch('/api/generate/status').then(jsonOrThrow<GenerateStatus>),

  generateImage: (prompt: string, model: string, size: string) =>
    fetch('/api/generate/image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, model, size }),
    }).then(jsonOrThrow<GenerateResult>),

  fetchAsset: (imageId: string) =>
    fetch(`/api/assets/${imageId}/raw`).then((res) => {
      if (!res.ok) throw new Error(res.statusText)
      return res.blob()
    }),

  tidyCheck: (items: Item[]) =>
    fetch('/api/tidy/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items }),
    }).then(jsonOrThrow<TidyCheck>),

  tidyApply: (items: Item[], ops: TidyOp[]) =>
    fetch('/api/tidy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items, ops }),
    }).then(jsonOrThrow<TidyResult>),

  setDemo: (enabled: boolean) =>
    fetch('/api/devices/demo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    }).then(jsonOrThrow<{ demo: boolean }>),

  composePreview: (project: Project, settings: JobSettings) =>
    fetch('/api/compose/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project, settings_body: settings }),
    }).then(jsonOrThrow<Preview>),
}