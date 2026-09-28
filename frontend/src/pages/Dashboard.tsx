import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, CheckCircle2, FileText, Layers, XCircle } from 'lucide-react'
import { ingest, templates } from '../lib/api'
import type { DocumentLogResponse, TemplateResponse } from '../lib/types'
import { StatusBadge, SourceBadge } from '../components/ui/Badge'
import { SkeletonCard, SkeletonRow } from '../components/ui/Skeleton'
import styles from './Dashboard.module.css'

interface Stat {
  label: string
  value: string | number
  sub?: string
  Icon: typeof FileText
  color: string
}

export function Dashboard() {
  const [logs, setLogs] = useState<DocumentLogResponse[]>([])
  const [tmpl, setTmpl] = useState<TemplateResponse[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      ingest.list({ limit: 10 }),
      templates.list(),
    ]).then(([l, t]) => {
      setLogs(l)
      setTmpl(t)
    }).finally(() => setLoading(false))
  }, [])

  const total = logs.length
  const success = logs.filter((l) => l.status === 'SUCCESS').length
  const failed = logs.filter((l) => l.status === 'FAILED').length
  const rate = total > 0 ? Math.round((success / total) * 100) : 0

  const stats: Stat[] = [
    { label: 'Extractions (shown)', value: total, sub: 'last 10 records', Icon: FileText, color: 'var(--color-accent)' },
    { label: 'Success rate', value: `${rate}%`, sub: `${success} succeeded`, Icon: CheckCircle2, color: 'var(--color-success)' },
    { label: 'Failed', value: failed, sub: 'need attention', Icon: XCircle, color: 'var(--color-error)' },
    { label: 'Templates', value: tmpl.length, sub: `${tmpl.filter(t => t.isActive).length} active`, Icon: Layers, color: 'var(--color-warning)' },
  ]

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Overview</h1>
          <p className={styles.sub}>Your extraction pipeline at a glance.</p>
        </div>
        <Link to="/submit" className={styles.ctaBtn}>
          Submit document <ArrowUpRight size={15} />
        </Link>
      </div>

      {/* Stat cards */}
      <div className={styles.statsGrid}>
        {loading
          ? Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
          : stats.map((s) => (
              <div key={s.label} className={styles.statCard}>
                <div className={styles.statTop}>
                  <span className={styles.statLabel}>{s.label}</span>
                  <s.Icon size={18} style={{ color: s.color, flexShrink: 0 }} />
                </div>
                <div className={styles.statValue}>{s.value}</div>
                <div className={styles.statSub}>{s.sub}</div>
              </div>
            ))}
      </div>

      {/* Recent activity */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Recent Activity</h2>
          <Link to="/logs" className={styles.viewAll}>View all →</Link>
        </div>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Document</th>
                <th>Status</th>
                <th>Source</th>
                <th>Processing</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {loading
                ? Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} cols={5} />)
                : logs.length === 0
                  ? (
                    <tr>
                      <td colSpan={5} className={styles.empty}>
                        No extractions yet.{' '}
                        <Link to="/submit">Submit your first document →</Link>
                      </td>
                    </tr>
                  )
                  : logs.map((log) => (
                    <tr key={log.id}>
                      <td className={styles.docCell}>
                        <span className={styles.docName}>
                          {log.fileName ?? (log.rawInput ? log.rawInput.slice(0, 40) + '…' : log.id.slice(0, 8))}
                        </span>
                      </td>
                      <td><StatusBadge status={log.status} /></td>
                      <td><SourceBadge source={log.source} /></td>
                      <td className={styles.mono}>
                        {log.processingMs != null ? `${log.processingMs}ms` : '—'}
                      </td>
                      <td className={styles.dateCell}>
                        {new Date(log.createdAt).toLocaleDateString()}
                      </td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
