/**
 * BatchContext.tsx — Keeps a running batch upload alive across pages.
 *
 * The batch lives in the dashboard layout instead of the Submit page, so the user can open Logs or
 * Settings while files are still being sent, and find the progress panel again when they return.
 *
 * It cannot survive closing or reloading the tab: files not yet sent exist only in memory (uploads
 * are not stored server-side). While any file is still unsent, the browser's "Leave site?" prompt is
 * shown for those cases. Documents already sent keep running on the server regardless.
 */

import { createContext, useEffect } from 'react'
import type { ReactNode } from 'react'
import { useBatchSubmit } from '../hooks/useBatchSubmit'

export const BatchContext = createContext<ReturnType<typeof useBatchSubmit> | null>(null)

export function BatchProvider({ children }: { children: ReactNode }) {
  const batch = useBatchSubmit()
  const unsent = batch.items.filter((i) => i.phase === 'waiting' || i.phase === 'submitting').length

  useEffect(() => {
    if (unsent === 0) return
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = '' // required by some browsers; the text itself is never shown
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [unsent])

  return <BatchContext.Provider value={batch}>{children}</BatchContext.Provider>
}
