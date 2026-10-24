/**
 * useFinishedDocs.ts — How many watched documents finished while the user was elsewhere.
 *
 * Polls the recent-documents list (one request, however many documents are watched) every few
 * seconds while anything is watched and the tab is visible. Opening the Logs page counts as
 * seeing them, so it clears the count.
 */

import { useCallback, useEffect, useState } from 'react'
import { ingest } from '../lib/api'
import { isInFlight } from '../lib/status'
import { subscribeWatched, unwatchDocuments, watchedIds } from '../lib/watch'

const POLL_INTERVAL_MS = 5000

export function useFinishedDocs(onLogsPage: boolean): number {
  const [finished, setFinished] = useState(0)

  const check = useCallback(async () => {
    const ids = watchedIds()
    if (ids.length === 0) { setFinished(0); return }
    try {
      const recent = await ingest.list({ limit: 100 })
      const done = recent.filter((d) => ids.includes(d.id) && !isInFlight(d.status)).map((d) => d.id)
      if (onLogsPage) { unwatchDocuments(done); setFinished(0) } else setFinished(done.length)
    } catch {
      // Transient failure: keep the previous count and try again on the next tick.
    }
  }, [onLogsPage])

  useEffect(() => {
    void check()
    const timer = setInterval(() => { if (!document.hidden) void check() }, POLL_INTERVAL_MS)
    const onVisible = () => { if (!document.hidden) void check() }
    document.addEventListener('visibilitychange', onVisible)
    const unsubscribe = subscribeWatched(() => void check())
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
      unsubscribe()
    }
  }, [check])

  return finished
}
