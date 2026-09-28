import type { ExtractionStatus, Source } from '../../lib/types'
import styles from './Badge.module.css'

type BadgeVariant = 'success' | 'error' | 'warning' | 'info' | 'neutral' | 'accent'

interface BadgeProps {
  variant?: BadgeVariant
  children: React.ReactNode
  dot?: boolean
}

export function Badge({ variant = 'neutral', children, dot = true }: BadgeProps) {
  return (
    <span className={[styles.badge, styles[variant]].join(' ')}>
      {dot && <span className={styles.dot} aria-hidden="true" />}
      {children}
    </span>
  )
}

// ── Domain-specific badge helpers ──────────────────────────────────────────

const STATUS_MAP: Record<ExtractionStatus, BadgeVariant> = {
  PENDING:    'neutral',
  PROCESSING: 'info',
  SUCCESS:    'success',
  FAILED:     'error',
  UNMATCHED:  'warning',
  NEEDS_REVIEW: 'accent',
}

const STATUS_LABELS: Record<ExtractionStatus, string> = {
  PENDING:    'Pending',
  PROCESSING: 'Processing',
  SUCCESS:    'Success',
  FAILED:     'Failed',
  UNMATCHED:  'Unmatched',
  NEEDS_REVIEW: 'Needs Review',
}

export function StatusBadge({ status }: { status: ExtractionStatus }) {
  return (
    <Badge variant={STATUS_MAP[status]}>
      {STATUS_LABELS[status]}
    </Badge>
  )
}

const SOURCE_LABELS: Record<Source, string> = {
  MANUAL:  'Manual',
  API:     'API',
  EMAIL:   'Email',
  WEBHOOK: 'Webhook',
}

export function SourceBadge({ source }: { source: Source }) {
  return (
    <Badge variant="neutral" dot={false}>
      {SOURCE_LABELS[source]}
    </Badge>
  )
}
