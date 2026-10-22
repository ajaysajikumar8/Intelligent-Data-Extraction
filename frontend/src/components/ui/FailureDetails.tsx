import { AlertCircle } from 'lucide-react'
import type { FailureInfo } from '../../lib/failure'
import styles from './FailureDetails.module.css'

/** Explains why an extraction failed, in terms the user can act on. */
export function FailureDetails({ failure }: { failure: FailureInfo }) {
  const title =
    failure.kind === 'fields' ? 'Validation Engine Failed'
    : failure.kind === 'message' ? failure.title
    : 'Extraction Failed'

  return (
    <div className={styles.box}>
      <div className={styles.head}>
        <AlertCircle size={18} aria-hidden="true" />
        <strong className={styles.title}>{title}</strong>
      </div>

      {failure.kind === 'message' && <p className={styles.message}>{failure.message}</p>}

      {failure.kind === 'fields' && (
        <>
          <p className={styles.intro}>
            The AI successfully extracted data, but it violated the strict rules of your template schema. Here is what needs fixing:
          </p>
          <div className={styles.issues}>
            {failure.issues.map((issue, i) => (
              <div key={i} className={styles.issue}>
                <span className={styles.dot} aria-hidden="true">●</span>
                <div>
                  <strong className={styles.field}>Field: <code className={styles.code}>{issue.field}</code></strong>
                  <span className={styles.issueText}>Issue: {issue.message}</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {failure.kind === 'unknown' && <pre className={styles.raw}>{JSON.stringify(failure.raw, null, 2)}</pre>}
    </div>
  )
}
