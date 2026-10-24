import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'
import { logs } from '../../lib/api'
import { retryability } from '../../lib/failure'
import type { DocumentLogResponse } from '../../lib/types'
import { Button } from './Button'
import styles from './RetryAction.module.css'

interface RetryActionProps {
  log: Pick<DocumentLogResponse, 'id' | 'status' | 'validationErrors' | 'rawInput' | 'fileName'>
  /** Called with the re-queued (PENDING) document so the caller can follow it. */
  onRetried: (log: DocumentLogResponse) => void
}

/** "Try again" for failed extractions that a retry can fix; explains why when it can't be offered. */
export function RetryAction({ log, onRetried }: RetryActionProps) {
  const [busy, setBusy] = useState(false)
  const can = retryability(log)
  if (can.kind === 'none') return null

  if (can.kind === 'needs-reupload') return <p className={styles.hint}>{can.reason}</p>

  const retry = async () => {
    setBusy(true)
    try {
      onRetried(await logs.retry(log.id))
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not retry this document')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={styles.row}>
      <Button variant="secondary" size="sm" loading={busy} onClick={retry}>
        <RefreshCw size={14} /> Try again
      </Button>
    </div>
  )
}
