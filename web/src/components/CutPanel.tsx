import { useEffect, useState } from 'react'
import { api } from '../api'
import { useStore } from '../store'
import type { DeviceInfo, SystemInfo } from '../types'
import { useEvents } from '../useEvents'

type JobState = {
  job_id: string
  state: 'queued' | 'running' | 'done' | 'cancelled' | 'failed'
  device: string | null
  bytes_sent: number
  bytes_total: number
  est_seconds: number
  error: string | null
  note: string | null
}

export default function CutPanel() {
  const doc = useStore((s) => s.doc)
  const settings = useStore((s) => s.jobSettings)
  const [devices, setDevices] = useState<DeviceInfo[]>([])
  const [info, setInfo] = useState<SystemInfo | null>(null)
  const [demo, setDemo] = useState(false)
  const [job, setJob] = useState<JobState | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.systemInfo().then((i) => {
      setInfo(i)
      setDevices(i.devices)
      setDemo(i.demo)
    }).catch(() => setError('backend unreachable'))
    fetch('/api/jobs/current')
      .then((r) => (r.ok ? r.json() : null))
      .then(setJob)
      .catch(() => {})
  }, [])

  useEvents((e) => {
    if (e.type === 'job.progress' || e.type === 'job.state') {
      const j = e.job as JobState
      setJob((prev) => ({ ...(prev ?? {}), ...j }))
    } else if (e.type === 'device.changed') {
      api.systemInfo().then((i) => setDevices(i.devices)).catch(() => {})
    }
  })

  async function toggleDemo() {
    try {
      const r = await api.setDemo(!demo)
      setDemo(r.demo)
      const i = await api.systemInfo()
      setInfo(i)
      setDevices(i.devices)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function send() {
    if (!doc) return
    setError(null)
    try {
      const r = await fetch('/api/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project: doc,
          job: demo ? { ...settings, device: 'demo' } : settings,
        }),
      })
      if (!r.ok) throw new Error((await r.json()).detail ?? r.statusText)
      const { job_id } = await r.json()
      setJob({
        job_id, state: 'queued', device: null, bytes_sent: 0,
        bytes_total: 0, est_seconds: 0, error: null, note: null,
      })
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function cancel() {
    const r = await fetch('/api/jobs/current', { method: 'DELETE' })
    if (!r.ok) setError((await r.json()).detail)
  }

  const active = job && (job.state === 'queued' || job.state === 'running')
  const demoJob = !!job?.device?.startsWith('demo')
  const pct = job && job.bytes_total > 0 ? Math.round((job.bytes_sent / job.bytes_total) * 100) : 0

  return (
    <div className="panel">
      <div className="panel-title">Cutter</div>
      <div className="device-line">
        {devices.length === 0 && <span className="hint">no PL2305 adapter found</span>}
        {devices.map((d) => (
          <span key={d.path} className={d.writable ? 'ok' : 'warn'}>
            {d.path === 'demo' ? 'demo (mock cutter)' : d.path} {d.writable ? 'ready' : 'no permission'}
          </span>
        ))}
        {info && !info.potrace && <span className="hint">(tracing unavailable: install potrace)</span>}
      </div>
      <label className="field check">
        <input type="checkbox" checked={demo} onChange={toggleDemo} />
        demo mode (mock cutter — nothing is sent to hardware)
      </label>
      <div className="send-row">
        <button onClick={send} disabled={!doc || !!active}>
          {active ? 'job running…' : demo ? 'send to demo cutter' : 'send to cutter'}
        </button>
        {active && <button onClick={cancel} className="danger">cancel</button>}
      </div>
      {error && <div className="error">{error}</div>}
      {job && (
        <div className="job">
          <div className="job-state">
            {job.state}
            {job.state === 'running' && job.device ? ` → ${job.device}` : ''}
          </div>
          {(job.state === 'running' || job.state === 'queued') && (
            <div className="progress">
              <div className="progress-bar" style={{ width: `${pct}%` }} />
            </div>
          )}
          <div className="hint">
            {job.bytes_sent}/{job.bytes_total} bytes
            {job.state === 'done' && demoJob && ' — demo cut finished; nothing was sent to hardware'}
            {job.state === 'done' && !demoJob && ' — stream finished (the machine has no feedback channel; check the cut)'}
            {job.state === 'cancelled' && !demoJob && ' — sending stopped; the machine may finish what it already buffered'}
            {job.state === 'cancelled' && demoJob && ' — demo send stopped'}
            {job.state === 'failed' && ` — ${job.error}`}
          </div>
          {job.note && <div className="hint warn-text">{job.note}</div>}
          {job.state === 'done' && !demoJob && (
            <div className="hint warn-text">
              nothing cut? the adapter may be stuck — run <code>setup/unstick-adapter.sh</code>
            </div>
          )}
        </div>
      )}
      {!demo && (
        <div className="hint">
          load material, press SETUP until &lt;ON&gt;, set origin with the position keys + ORIGIN SET
        </div>
      )}
      {demo && (
        <div className="hint">
          demo mode: the job runs against a simulated cutter with paced progress; the exact
          HPGL stream is saved under data/jobs/ so it can be inspected like a real job
        </div>
      )}
    </div>
  )
}