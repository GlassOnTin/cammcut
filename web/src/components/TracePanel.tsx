import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { uid, useStore } from '../store'
import { type Mat, mul } from '../geom/matrix'
import type { GenerateStatus, ImportResult } from '../types'

/** Raster → vector via backend potrace. The canvas preview shows the
 *  threshold silhouette the trace will use (potrace is 1-bit). */
export default function TracePanel() {
  const [file, setFile] = useState<File | null>(null)
  const [imgUrl, setImgUrl] = useState('')
  const [imgSize, setImgSize] = useState<{ w: number; h: number } | null>(null)
  const [threshold, setThreshold] = useState(128)
  const [invert, setInvert] = useState(false)
  const [turdsize, setTurdsize] = useState(2)
  const [alphamax, setAlphamax] = useState(1.0)
  const [opttolerance, setOpttolerance] = useState(0.2)
  const [potrace, setPotrace] = useState<boolean | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const imgElRef = useRef<HTMLImageElement | null>(null)
  // text→image generation (nexos.ai); only offered when the server has a key
  const [genStatus, setGenStatus] = useState<GenerateStatus | null>(null)
  const [genPrompt, setGenPrompt] = useState('')
  const [genModel, setGenModel] = useState('')
  const [genSize, setGenSize] = useState('1024x1024')
  const [genBusy, setGenBusy] = useState(false)
  const [genError, setGenError] = useState('')

  useEffect(() => {
    fetch('/api/trace/status').then((r) => r.json())
      .then((j) => setPotrace(Boolean(j.potrace)))
      .catch(() => setPotrace(null))
    api.generateStatus().then((j) => {
      setGenStatus(j)
      if (j.configured) {
        setGenModel((m) => m || localStorage.getItem('cammcut-gen-model') || j.default_model)
      }
    }).catch(() => setGenStatus(null))
  }, [])

  // load the picked image, remember its natural size
  useEffect(() => {
    if (!file) { setImgUrl(''); setImgSize(null); setResult(null); return }
    const url = URL.createObjectURL(file)
    setImgUrl(url)
    const img = new Image()
    img.onload = () => setImgSize({ w: img.naturalWidth, h: img.naturalHeight })
    img.src = url
    imgElRef.current = img
    return () => URL.revokeObjectURL(url)
  }, [file])

  // threshold preview on canvas
  useEffect(() => {
    const img = imgElRef.current
    const canvas = canvasRef.current
    if (!img || !canvas || !img.naturalWidth) return
    const maxSide = 280
    const scale = Math.min(1, maxSide / Math.max(img.naturalWidth, img.naturalHeight))
    const w = Math.max(1, Math.round(img.naturalWidth * scale))
    const h = Math.max(1, Math.round(img.naturalHeight * scale))
    canvas.width = w
    canvas.height = h
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.drawImage(img, 0, 0, w, h)
    const data = ctx.getImageData(0, 0, w, h)
    const px = data.data
    for (let i = 0; i < px.length; i += 4) {
      const g = 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2]
      let v: number
      if (invert) v = g > threshold ? 0 : 255
      else v = g <= threshold ? 0 : 255
      px[i] = px[i + 1] = px[i + 2] = v
    }
    ctx.putImageData(data, 0, 0)
  }, [imgSize, threshold, invert])

  // f defaults to the picked file; generation passes the fresh File
  // explicitly because state updates are not synchronous
  async function trace(f: File | null = file) {
    if (!f) return
    setBusy(true)
    setError('')
    try {
      const r = await api.traceImage(f, { threshold, invert, turdsize, alphamax, opttolerance })
      setResult(r)
    } catch (e) {
      setResult(null)
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function doGenerate() {
    const prompt = genPrompt.trim()
    if (!prompt || genBusy || !genModel) return
    setGenBusy(true)
    setGenError('')
    try {
      const g = await api.generateImage(prompt, genModel, genSize)
      const blob = await api.fetchAsset(g.image_id)
      const f = new File([blob], 'generated.png', { type: 'image/png' })
      setFile(f)
      // auto-trace once: the user lands on the confirm flow (threshold,
      // invert, re-trace) instead of a second click
      await trace(f)
    } catch (e) {
      setGenError(e instanceof Error ? e.message : String(e))
    } finally {
      setGenBusy(false)
    }
  }

  function insert() {
    if (!result) return
    const st = useStore.getState()
    if (!st.doc) return
    // items carry their own scale transform (96 dpi); compose a translation
    // that centres the traced image on the current view
    const v = st.view
    const e = v.x + v.w / 2 - result.width_mm / 2
    const f = v.y + v.h / 2 - result.height_mm / 2
    const t: Mat = [1, 0, 0, 1, e, f]
    const items = result.items.map((it) => ({
      id: uid(), kind: 'path' as const, d: it.d,
      transform: mul(t, it.transform as Mat),
    }))
    st.insertItems('traced', items)
  }

  return (
    <div className="panel shapes-panel">
      <div className="panel-title">Trace</div>
      {potrace === false && (
        <div className="hint warn">potrace is not installed on the server — run: sudo apt install potrace</div>
      )}
      {genStatus?.configured ? (
        <div className="gen-section">
          <textarea
            className="gen-prompt"
            rows={2}
            placeholder="describe the art to generate — traced as a 1-bit silhouette"
            value={genPrompt}
            disabled={genBusy}
            onChange={(e) => setGenPrompt(e.target.value)}
          />
          <div className="field-row">
            <label className="field">
              model
              <select value={genModel} disabled={genBusy}
                onChange={(e) => {
                  setGenModel(e.target.value)
                  localStorage.setItem('cammcut-gen-model', e.target.value)
                }}>
                {genStatus.models.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </label>
            <label className="field">
              size
              <select value={genSize} disabled={genBusy}
                onChange={(e) => setGenSize(e.target.value)}>
                {genStatus.sizes.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
          </div>
          <button className="shape-add" disabled={!genPrompt.trim() || genBusy || !genModel}
            onClick={doGenerate}>
            {genBusy ? 'generating…' : 'generate & trace'}
          </button>
          {genError && <div className="error">{genError}</div>}
        </div>
      ) : genStatus ? (
        <div className="hint">AI image generation is off — set CAMMCUT_NEXOS_KEY on the server</div>
      ) : null}
      {genStatus?.configured && <div className="hint">or trace an image file:</div>}
      <label className="field">
        image
        <input type="file" accept="image/png,image/jpeg,image/webp,image/bmp,image/gif"
          onChange={(e) => { setFile(e.target.files?.[0] ?? null) }} />
      </label>
      {imgUrl && (
        <canvas ref={canvasRef} className="trace-preview" />
      )}
      {imgSize && (
        <div className="hint">source {imgSize.w} × {imgSize.h} px</div>
      )}
      {file && (
        <>
          <label className="field">
            threshold {threshold}
            <input type="range" min={0} max={255} value={threshold}
              onChange={(e) => setThreshold(parseInt(e.target.value))} />
          </label>
          <label className="field check">
            <input type="checkbox" checked={invert}
              onChange={(e) => setInvert(e.target.checked)} />
            invert (trace light-on-dark)
          </label>
          <details className="advanced">
            <summary>advanced</summary>
            <label className="field">
              speckle (turdsize) {turdsize}
              <input type="range" min={0} max={20} value={turdsize}
                onChange={(e) => setTurdsize(parseInt(e.target.value))} />
            </label>
            <label className="field">
              corner smooth (alphamax) {alphamax.toFixed(2)}
              <input type="range" min={0} max={1.334} step={0.01} value={alphamax}
                onChange={(e) => setAlphamax(parseFloat(e.target.value))} />
            </label>
            <label className="field">
              fit tolerance {opttolerance.toFixed(2)}
              <input type="range" min={0} max={5} step={0.05} value={opttolerance}
                onChange={(e) => setOpttolerance(parseFloat(e.target.value))} />
            </label>
          </details>
        </>
      )}
      {error && <div className="error">{error}</div>}
      {result && (
        <div className="text-preview">
          <div className="hint">{result.width_mm.toFixed(1)} × {result.height_mm.toFixed(1)} mm · {result.items.length} path{result.items.length === 1 ? '' : 's'}</div>
          {result.warnings.map((w, i) => <div key={i} className="hint warn">{w}</div>)}
        </div>
      )}
      <button className="shape-add" disabled={!file || busy || potrace === false} onClick={() => trace()}>
        {busy ? 'tracing…' : 'trace'}
      </button>
      <button className="shape-add" disabled={!result} onClick={insert}>
        add paths to artboard
      </button>
      <div className="hint">trace is 1-bit: a threshold silhouette, not a colour-aware trace</div>
    </div>
  )
}