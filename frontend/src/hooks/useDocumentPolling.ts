/**
 * useDocumentPolling.ts — Follow a document through the extraction queue.
 *
 * `POST /ingest` returns immediately with a PENDING log; the pipeline runs in
 * the background. This hook polls `GET /logs/{id}` until the status is final.
 *
 * - Network blips and 5xx responses are ignored; polling simply continues.
 * - A 4xx (expired session, document gone) can never succeed on retry, so polling stops.
 * - Gives up after MAX_WAIT_MS (> the backend job timeout) and reports `timedOut`
 *   so the UI can say the job is still running instead of spinning forever.
 * - Stops on unmount or when `documentId` changes.
 */

import { useEffect, useState } from 'react'
import { ApiError, logs } from '../lib/api'
import { isInFlight } from '../lib/status'
import type { DocumentLogDetailResponse } from '../lib/types'

const POLL_INTERVAL_MS = 2000
const MAX_WAIT_MS = 8 * 60 * 1000 // > the backend job timeout (450s)

export function useDocumentPolling(documentId: string | null) {
  const [log, setLog] = useState<DocumentLogDetailResponse | null>(null)
  const [timedOut, setTimedOut] = useState(false)

  useEffect(() => {
    setLog(null)
    setTimedOut(false)
    if (!documentId) return

    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const startedAt = Date.now()

    const tick = async () => {
      try {
        const next = await logs.get(documentId)
        if (cancelled) return
        setLog(next)
        if (!isInFlight(next.status)) return
      } catch (e) {
        if (e instanceof ApiError && e.status >= 400 && e.status < 500) return
        // Network blip or 5xx: keep polling.
      }
      if (cancelled) return
      if (Date.now() - startedAt > MAX_WAIT_MS) {
        setTimedOut(true)
        return
      }
      timer = setTimeout(tick, POLL_INTERVAL_MS)
    }

    tick()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [documentId])

  return { log, timedOut }
}
