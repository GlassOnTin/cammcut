import { useEffect } from 'react'

export type ServerEvent = { type: string; [k: string]: unknown }

export function useEvents(onEvent: (e: ServerEvent) => void) {
  useEffect(() => {
    const es = new EventSource('/api/events')
    es.onmessage = (m) => {
      try {
        onEvent(JSON.parse(m.data))
      } catch {
        /* ignore malformed */
      }
    }
    return () => es.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}