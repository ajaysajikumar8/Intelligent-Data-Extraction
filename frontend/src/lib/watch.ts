/**
 * Documents this browser submitted and has not seen finish yet ("watched"). The sidebar badge counts
 * the ones that have finished since, so a user who left the Submit page still learns about them
 * (issue #18). Stored in localStorage as { documentId: addedAtMs } so it survives reloads and is
 * shared by tabs; every read and write tolerates storage being unavailable.
 */

const KEY = 'ide:watching'
const CHANGED_EVENT = 'ide:watching-changed'
const MAX_AGE_MS = 24 * 60 * 60 * 1000

type Watched = Record<string, number>

function read(): Watched {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(KEY) ?? '{}')
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {}
    const now = Date.now()
    return Object.fromEntries(
      Object.entries(parsed as Record<string, unknown>).filter(
        (e): e is [string, number] => typeof e[1] === 'number' && now - e[1] < MAX_AGE_MS,
      ),
    )
  } catch {
    return {}
  }
}

function write(next: Watched) {
  try {
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    // Storage unavailable (private mode, quota): the badge is a convenience, not a requirement.
  }
  window.dispatchEvent(new Event(CHANGED_EVENT))
}

export function watchDocuments(ids: string[]) {
  if (ids.length === 0) return
  const next = read()
  const now = Date.now()
  ids.forEach((id) => { next[id] = next[id] ?? now })
  write(next)
}

export function unwatchDocuments(ids: string[]) {
  const current = read()
  if (!ids.some((id) => id in current)) return
  write(Object.fromEntries(Object.entries(current).filter(([id]) => !ids.includes(id))))
}

export function watchedIds(): string[] {
  return Object.keys(read())
}

/** Calls `cb` when the watch list changes in this tab or another one. */
export function subscribeWatched(cb: () => void): () => void {
  const onStorage = (e: StorageEvent) => { if (e.key === KEY || e.key === null) cb() }
  window.addEventListener(CHANGED_EVENT, cb)
  window.addEventListener('storage', onStorage)
  return () => {
    window.removeEventListener(CHANGED_EVENT, cb)
    window.removeEventListener('storage', onStorage)
  }
}
