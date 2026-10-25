import { useEffect, useState } from 'react'
import { History } from 'lucide-react'
import { activity } from '../lib/api'
import { actionLabel, CATEGORY_OPTIONS } from '../lib/activity'
import type { ActivityCategory, ActivityLogEntry } from '../lib/types'
import { getUser } from '../lib/auth'
import { Skeleton } from '../components/ui/Skeleton'
import styles from './Activity.module.css'

const PAGE_SIZE = 25

export function Activity() {
  const isOwner = getUser()?.role === 'OWNER'
  const [entries, setEntries] = useState<ActivityLogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [skip, setSkip] = useState(0)
  const [category, setCategory] = useState<ActivityCategory | ''>('')

  useEffect(() => {
    if (!isOwner) return
    setLoading(true)
    setError('')
    activity.list({ skip, limit: PAGE_SIZE, category: category || undefined })
      .then(setEntries)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Could not load activity'))
      .finally(() => setLoading(false))
  }, [skip, category, isOwner])

  if (!isOwner) {
    return (
      <div className={styles.page}>
        <h1 className={styles.title}>Activity</h1>
        <p className={styles.notice}>Only workspace owners can see the activity log.</p>
      </div>
    )
  }

  return (
    <div className={styles.page}>
      <div>
        <h1 className={styles.title}>Activity</h1>
        <p className={styles.sub}>Who changed what in this workspace, newest first. Secret values are never recorded.</p>
      </div>

      <div className={styles.filters}>
        <label className={styles.filterLabel} htmlFor="activity-category">Show</label>
        <select
          id="activity-category"
          className={styles.select}
          value={category}
          onChange={(e) => { setCategory(e.target.value as ActivityCategory | ''); setSkip(0) }}
        >
          <option value="">Everything</option>
          {CATEGORY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>

      {error && <p className={styles.error} role="alert">{error}</p>}

      <ul className={styles.list}>
        {loading
          ? Array.from({ length: 6 }).map((_, i) => (
              <li key={i} className={styles.item}><Skeleton height={14} width="60%" /><Skeleton height={12} width="90%" /></li>
            ))
          : entries.length === 0
            ? (
              <li className={styles.empty}>
                <History size={36} aria-hidden="true" />
                <p>Nothing recorded yet{category ? ' in this category' : ''}.</p>
              </li>
            )
            : entries.map((e) => (
              <li key={e.id} className={styles.item}>
                <div className={styles.row}>
                  <span className={styles.action}>{actionLabel(e.action)}</span>
                  <time className={styles.time} dateTime={e.createdAt}>{new Date(e.createdAt).toLocaleString()}</time>
                </div>
                <p className={styles.summary}>{e.summary}</p>
                <p className={styles.meta}>
                  {e.actorLabel}{e.ipAddress ? ` · ${e.ipAddress}` : ''}
                </p>
              </li>
            ))}
      </ul>

      <div className={styles.pagination}>
        <button className={styles.pageBtn} onClick={() => setSkip(Math.max(0, skip - PAGE_SIZE))} disabled={skip === 0 || loading}>
          ← Previous
        </button>
        <span className={styles.pageInfo}>{entries.length > 0 ? `Showing ${skip + 1}–${skip + entries.length}` : ''}</span>
        <button className={styles.pageBtn} onClick={() => setSkip(skip + PAGE_SIZE)} disabled={entries.length < PAGE_SIZE || loading}>
          Next →
        </button>
      </div>
    </div>
  )
}
