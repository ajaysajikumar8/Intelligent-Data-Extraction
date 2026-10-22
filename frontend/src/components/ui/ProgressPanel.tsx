import { Check, Loader2 } from 'lucide-react'
import type { DocumentLogResponse } from '../../lib/types'
import { PROGRESS_STEPS, describeProgress, formatElapsed } from '../../lib/progress'
import { useElapsedSeconds } from '../../hooks/useElapsed'
import styles from './ProgressPanel.module.css'

const SLOW_AFTER_SECONDS = 90

interface ProgressPanelProps {
  log: DocumentLogResponse
  /** The client stopped polling; the job may still be running on the server. */
  timedOut?: boolean
}

/** Shows where a queued/running extraction is, including automatic retries. */
export function ProgressPanel({ log, timedOut = false }: ProgressPanelProps) {
  const view = describeProgress(log.status, log.progress)
  const elapsed = useElapsedSeconds(log.createdAt, true)
  const showSlowHint = timedOut || elapsed >= SLOW_AFTER_SECONDS

  return (
    <div className={[styles.panel, view.retrying ? styles.retrying : ''].join(' ')}>
      <div className={styles.head} role="status" aria-live="polite">
        <Loader2 size={20} className={styles.spinner} aria-hidden="true" />
        <div>
          <p className={styles.headline}>{timedOut ? 'Still working on it' : view.headline}</p>
          <p className={styles.detail}>{timedOut ? 'This is taking longer than expected, but it keeps running in the background.' : view.detail}</p>
        </div>
      </div>

      <ol className={styles.steps} aria-label="Extraction steps">
        {PROGRESS_STEPS.map((label, i) => {
          const state = i < view.step ? 'done' : i === view.step ? 'current' : 'todo'
          return (
            <li key={label} className={[styles.step, styles[state]].join(' ')} aria-current={state === 'current' ? 'step' : undefined}>
              <span className={styles.marker} aria-hidden="true">{state === 'done' ? <Check size={11} /> : i + 1}</span>
              {label}
            </li>
          )
        })}
      </ol>

      <p className={styles.meta}>
        {log.status === 'PENDING' ? 'Waiting' : 'Running'} for {formatElapsed(elapsed)}
      </p>

      {showSlowHint && (
        <p className={styles.hint}>
          This is taking longer than usual. You can leave this page; the result will appear in Extraction Logs.
        </p>
      )}
    </div>
  )
}
