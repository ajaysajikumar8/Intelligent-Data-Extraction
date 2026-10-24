/**
 * useBatchSubmit.ts — Submit several files and follow each to a final status.
 *
 * Each file becomes its own document via `POST /ingest` (one DocumentLog, one
 * credit, one webhook each), so partial failures stay isolated. The browser keeps
 * at most BATCH_CONCURRENCY documents in flight at a time: it submits a file,
 * polls it until it is final, then takes the next. That keeps one batch from
 * filling the shared server queue (the server also enforces a per-workspace cap).
 *
 * - A per-file error (bad file, extraction failure) only marks that row.
 * - A capacity error (monthly quota, workspace cap, queue full) stops the batch:
 *   every file not yet submitted is marked "not submitted" with the reason.
 * - `cancel()` stops new submissions; documents already submitted keep running
 *   on the server and still appear in Logs.
 * - Files not yet submitted live only in this tab, so the page must stay open.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, ingest, logs } from '../lib/api'
import { isInFlight } from '../lib/status'
import { unwatchDocuments, watchDocuments } from '../lib/watch'
import type { DocumentLogDetailResponse } from '../lib/types'

export const BATCH_CONCURRENCY = 3
const POLL_INTERVAL_MS = 2000
const MAX_WAIT_MS = 8 * 60 * 1000 // > the backend job timeout (450s)

export type BatchPhase = 'waiting' | 'submitting' | 'running' | 'finished' | 'not-submitted'

export interface BatchItem {
  key: string
  file: File
  phase: BatchPhase
  /** Latest log once submitted; final when `phase === 'finished'`. */
  log: DocumentLogDetailResponse | null
  /** Why the file was not submitted (or its result could not be followed). */
  error: string | null
}

/** Errors that mean "nothing more will be accepted right now", not "this file is bad". */
function isCapacityError(e: unknown): boolean {
  return e instanceof ApiError && (e.status === 429 || e.status === 503)
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

export function useBatchSubmit() {
  const [items, setItems] = useState<BatchItem[]>([])
  const [running, setRunning] = useState(false)
  // Bumped by cancel/reset/unmount so stale workers stop touching state.
  const runId = useRef(0)
  // Set when the batch must stop submitting (capacity error or cancel); read by every worker.
  const stopReason = useRef<string | null>(null)

  useEffect(() => () => { runId.current += 1 }, [])

  const patch = useCallback((key: string, change: Partial<BatchItem>, run: number) => {
    if (run !== runId.current) return
    setItems((prev) => prev.map((it) => (it.key === key ? { ...it, ...change } : it)))
  }, [])

  const start = useCallback(async (files: File[], templateId?: string) => {
    const run = ++runId.current
    stopReason.current = null
    const initial: BatchItem[] = files.map((file, i) => ({
      key: `${run}-${i}`, file, phase: 'waiting', log: null, error: null,
    }))
    setItems(initial)
    setRunning(true)

    const pending = [...initial]

    const worker = async () => {
      for (;;) {
        if (run !== runId.current) return
        const item = pending.shift()
        if (!item) return
        if (stopReason.current) {
          patch(item.key, { phase: 'not-submitted', error: stopReason.current }, run)
          continue
        }

        patch(item.key, { phase: 'submitting' }, run)
        let submitted
        try {
          submitted = await ingest.submit({ file: item.file, templateId })
        } catch (e) {
          const message = e instanceof Error ? e.message : 'Submission failed'
          if (isCapacityError(e)) stopReason.current ??= message
          patch(item.key, { phase: 'not-submitted', error: message }, run)
          continue
        }

        watchDocuments([submitted.id])
        patch(item.key, { phase: 'running', log: { ...submitted, webhookDeliveries: [] } }, run)
        const startedAt = Date.now()
        for (;;) {
          await sleep(POLL_INTERVAL_MS)
          if (run !== runId.current) return
          try {
            const next = await logs.get(submitted.id)
            patch(item.key, { log: next }, run)
            if (!isInFlight(next.status)) { unwatchDocuments([submitted.id]); break }
          } catch (e) {
            // Network blip / 5xx: keep polling. A 4xx can never succeed on retry.
            if (e instanceof ApiError && e.status >= 400 && e.status < 500) {
              patch(item.key, { phase: 'finished', error: 'Could not read the result. Check the Logs page.' }, run)
              break
            }
          }
          if (Date.now() - startedAt > MAX_WAIT_MS) {
            patch(item.key, { phase: 'finished', error: 'Still processing. Check the Logs page for the result.' }, run)
            break
          }
        }
        patch(item.key, { phase: 'finished' }, run)
      }
    }

    await Promise.all(Array.from({ length: Math.min(BATCH_CONCURRENCY, files.length) }, worker))
    if (run === runId.current) setRunning(false)
  }, [patch])

  /** Stop submitting new files. Unsubmitted rows are marked; documents already submitted are still followed. */
  const cancel = useCallback(() => {
    stopReason.current ??= 'Cancelled'
  }, [])

  const reset = useCallback(() => {
    runId.current += 1
    setRunning(false)
    setItems([])
  }, [])

  return { items, running, start, cancel, reset }
}
