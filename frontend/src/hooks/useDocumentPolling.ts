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

/** `attempt` restarts polling for the same document id, e.g. after a retry. */
export function useDocumentPolling(documentId: string | null, attempt = 0) {
  // Tagged with the document+attempt it belongs to, so a retry never shows the previous attempt's result.
  const [polled, setPolled] = useState<{ key: string; log: DocumentLogDetailResponse } | null>(null)
  const [timedOut, setTimedOut] = useState(false)

  useEffect(() => {
    setPolled(null)
    setTimedOut(false)
    if (!documentId) return
    const key = `${documentId}:${attempt}`

    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const startedAt = Date.now()

    const tick = async () => {
      try {
        const next = await logs.get(documentId)
        if (cancelled) return
        setPolled({ key, log: next })
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
  }, [documentId, attempt])

  const log = polled && polled.key === `${documentId}:${attempt}` ? polled.log : null
  return { log, timedOut }
}
