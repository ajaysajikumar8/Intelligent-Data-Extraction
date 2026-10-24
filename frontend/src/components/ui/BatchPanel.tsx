import { Link } from 'react-router-dom'
import { Download, ExternalLink } from 'lucide-react'
import { BATCH_CONCURRENCY, type BatchItem } from '../../hooks/useBatchSubmit'
import { describeFailure } from '../../lib/failure'
import { exportLogsAsCsv, exportLogsAsJson } from '../../lib/export'
import { StatusBadge } from './Badge'
import { Button } from './Button'
import styles from './BatchPanel.module.css'

const PHASE_LABELS: Record<string, string> = {
  waiting: 'Waiting',
  submitting: 'Uploading…',
  running: 'Processing…',
  'not-submitted': 'Not submitted',
}

function rowDetail(item: BatchItem): string | null {
  if (item.error) return item.error
  const failure = describeFailure(item.log?.validationErrors)
  if (item.log?.status === 'FAILED' && failure?.kind === 'message') return failure.message
  if (failure?.kind === 'fields') return `${failure.issues.length} field(s) failed validation`
  return null
}

interface BatchPanelProps {
  items: BatchItem[]
  running: boolean
  onCancel: () => void
  onReset: () => void
}

export function BatchPanel({ items, running, onCancel, onReset }: BatchPanelProps) {
  const finished = items.filter((i) => i.phase === 'finished' || i.phase === 'not-submitted').length
  const succeeded = items.filter((i) => i.log?.status === 'SUCCESS').length
  const exportable = items
    .map((i) => i.log)
    .filter((l): l is NonNullable<typeof l> => !!l && !!l.extractedJson)

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div>
          <h3 className={styles.title}>Batch extraction</h3>
          <p className={styles.summary} aria-live="polite">
            {finished} of {items.length} finished · {succeeded} succeeded
          </p>
        </div>
        <div className={styles.actions}>
          {running ? (
            <Button variant="secondary" size="sm" onClick={onCancel}>Stop submitting</Button>
          ) : (
            <Button variant="ghost" size="sm" onClick={onReset}>Clear</Button>
          )}
          {exportable.length > 0 && (
            <>
              <Button variant="ghost" size="sm" onClick={() => exportLogsAsJson(exportable, 'batch_extraction')}>
                <Download size={14} /> JSON
              </Button>
              <Button variant="ghost" size="sm" onClick={() => exportLogsAsCsv(exportable, 'batch_extraction')}>
                <Download size={14} /> CSV
              </Button>
            </>
          )}
        </div>
      </div>

      {running && (
        <p className={styles.note}>
          Keep this page open until every file has been submitted ({BATCH_CONCURRENCY} are processed at a time).
          Files already submitted keep running even if you leave.
        </p>
      )}

      <ul className={styles.list}>
        {items.map((item) => {
          const detail = rowDetail(item)
          return (
            <li key={item.key} className={styles.row}>
              <div className={styles.rowMain}>
                <span className={styles.fileName} title={item.file.name}>{item.file.name}</span>
                {detail && <span className={styles.detail}>{detail}</span>}
              </div>
              <div className={styles.rowStatus}>
                {item.phase === 'finished' && item.log ? (
                  <StatusBadge status={item.log.status} />
                ) : (
                  <span className={styles.phase} data-phase={item.phase}>
                    {item.phase === 'finished' ? 'Check logs' : PHASE_LABELS[item.phase]}
                  </span>
                )}
              </div>
            </li>
          )
        })}
      </ul>

      <div className={styles.footer}>
        <Link to="/logs" className={styles.logsLink}>
          View details in Extraction Logs <ExternalLink size={13} />
        </Link>
      </div>
    </div>
  )
}

