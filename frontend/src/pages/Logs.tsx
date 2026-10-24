import { Fragment, useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, Webhook, FileText, CheckCircle2, XCircle, Download, FileQuestion } from 'lucide-react'
import { ingest, logs as logsApi, templates as templatesApi } from '../lib/api'
import type { DocumentLogResponse, DocumentLogDetailResponse, ExtractionStatus, Source, TemplateResponse } from '../lib/types'
import { StatusBadge, SourceBadge } from '../components/ui/Badge'
import { SkeletonRow } from '../components/ui/Skeleton'
import { Drawer } from '../components/ui/Drawer'
import { Button } from '../components/ui/Button'
import { describeFailure } from '../lib/failure'
import { FailureDetails } from '../components/ui/FailureDetails'
import { RetryAction } from '../components/ui/RetryAction'
import { ReviewForm } from '../components/ReviewForm'
import { exportLogsAsCsv, exportLogsAsJson } from '../lib/export'
import { isInFlight } from '../lib/status'
import { progressHint } from '../lib/progress'
import { ProgressPanel } from '../components/ui/ProgressPanel'
import styles from './Logs.module.css'

const STATUS_OPTIONS: ExtractionStatus[] = ['SUCCESS', 'NEEDS_REVIEW', 'FAILED', 'UNMATCHED', 'PENDING', 'PROCESSING']
const SOURCE_OPTIONS: Source[] = ['MANUAL', 'API', 'EMAIL', 'WEBHOOK']
const PAGE_SIZE = 20
const REFRESH_MS = 3000

export function Logs() {
  const [logs, setLogs] = useState<DocumentLogResponse[]>([])
  const [details, setDetails] = useState<Record<string, DocumentLogDetailResponse>>({})
  const [loading, setLoading] = useState(true)
  const [skip, setSkip] = useState(0)
  const [filterStatus, setFilterStatus] = useState<ExtractionStatus | ''>('')
  const [filterSource, setFilterSource] = useState<Source | ''>('')
  const [expanded, setExpanded] = useState<string | null>(null)
  // Loaded the first time a NEEDS_REVIEW document is opened: the review form needs field types.
  const [templateList, setTemplateList] = useState<TemplateResponse[] | null>(null)


  useEffect(() => {
    setLoading(true)
    ingest.list({
      skip,
      limit: PAGE_SIZE,
      status: filterStatus || undefined,
      source: filterSource || undefined,
    })
      .then(setLogs)
      .finally(() => setLoading(false))
  }, [skip, filterStatus, filterSource])

  // Extractions run in a background queue: keep the list fresh while any row is still in flight.
  const hasInFlight = logs.some((l) => isInFlight(l.status))
  useEffect(() => {
    if (!hasInFlight) return
    const timer = setInterval(() => {
      ingest.list({
        skip,
        limit: PAGE_SIZE,
        status: filterStatus || undefined,
        source: filterSource || undefined,
      })
        .then(setLogs)
        .catch(() => {}) // transient failure: try again on the next tick
    }, REFRESH_MS)
    return () => clearInterval(timer)
  }, [hasInFlight, skip, filterStatus, filterSource])

  // An open drawer loaded while a job was in flight goes stale when the job finishes.
  useEffect(() => {
    if (!expanded) return
    const row = logs.find((l) => l.id === expanded)
    const detail = details[expanded]
    if (row && detail && (row.status !== detail.status || JSON.stringify(row.progress) !== JSON.stringify(detail.progress))) {
      logsApi.get(expanded).then((data) => setDetails((prev) => ({ ...prev, [expanded]: data })))
    }
  }, [logs, expanded, details])

  const openStatus = expanded ? details[expanded]?.status : undefined
  useEffect(() => {
    if (openStatus !== 'NEEDS_REVIEW' || templateList) return
    templatesApi.list().then(setTemplateList).catch(() => setTemplateList([]))
  }, [openStatus, templateList])

  const handleCorrected = (updated: DocumentLogDetailResponse) => {
    setDetails((prev) => ({ ...prev, [updated.id]: updated }))
    setLogs((prev) => prev.map((l) => (l.id === updated.id ? { ...l, status: updated.status, extractedJson: updated.extractedJson } : l)))
  }

  const handleRetried = (updated: DocumentLogResponse) => {
    setLogs((prev) => prev.map((l) => (l.id === updated.id ? updated : l)))
    setDetails((prev) => ({ ...prev, [updated.id]: { ...updated, webhookDeliveries: prev[updated.id]?.webhookDeliveries ?? [] } }))
  }

  const toggle = (id: string) => {
    setExpanded((prev) => (prev === id ? null : id))
    if (!details[id] && expanded !== id) {
      logsApi.get(id).then((data) => setDetails((prev) => ({ ...prev, [id]: data })))
    }
  }

  const handleExportJson = () => exportLogsAsJson(logs)

  const handleExportCsv = () => exportLogsAsCsv(logs)

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Extraction Logs</h1>
          <p className={styles.sub}>Full history of all document ingestion runs.</p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <Button variant="secondary" size="sm" onClick={handleExportJson} disabled={logs.length === 0}>
            <Download size={14} /> JSON
          </Button>
          <Button variant="secondary" size="sm" onClick={handleExportCsv} disabled={logs.length === 0}>
            <Download size={14} /> CSV
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className={styles.filters}>
        <select
          className={styles.select}
          value={filterStatus}
          onChange={(e) => { setFilterStatus(e.target.value as ExtractionStatus | ''); setSkip(0) }}
          aria-label="Filter by status"
        >
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select
          className={styles.select}
          value={filterSource}
          onChange={(e) => { setFilterSource(e.target.value as Source | ''); setSkip(0) }}
          aria-label="Filter by source"
        >
          <option value="">All sources</option>
          {SOURCE_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {/* Table */}
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th style={{ width: 32 }} />
              <th>Document</th>
              <th>Status</th>
              <th>Source</th>
              <th>Processing</th>
              <th>Date</th>
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 8 }).map((_, i) => <SkeletonRow key={i} cols={6} />)
              : logs.length === 0
                ? (
                  <tr>
                    <td colSpan={6} className={styles.empty}>No logs found for the selected filters.</td>
                  </tr>
                )
                : logs.map((log) => (
                  <Fragment key={log.id}>
                    <tr
                      className={styles.row}
                      onClick={() => toggle(log.id)}
                    >
                      <td className={styles.chevronCell}>
                        {expanded === log.id
                          ? <ChevronDown size={14} />
                          : <ChevronRight size={14} />}
                      </td>
                      <td className={styles.docCell}>
                        {log.fileName ?? (log.rawInput ? log.rawInput.slice(0, 50) + '…' : log.id.slice(0, 12))}
                      </td>
                      <td>
                        <StatusBadge status={log.status} />
                        {progressHint(log.status, log.progress) && (
                          <span className={styles.rowHint}>{progressHint(log.status, log.progress)}</span>
                        )}
                      </td>
                      <td><SourceBadge source={log.source} /></td>
                      <td className={styles.mono}>
                        {log.processingMs != null ? `${log.processingMs}ms` : '—'}
                      </td>
                      <td className={styles.dateCell}>
                        {new Date(log.createdAt).toLocaleString()}
                      </td>
                    </tr>
                  </Fragment>
                ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className={styles.pagination}>
        <button
          className={styles.pageBtn}
          onClick={() => setSkip(Math.max(0, skip - PAGE_SIZE))}
          disabled={skip === 0}
        >
          ← Previous
        </button>
        <span className={styles.pageInfo}>
          Showing {skip + 1}–{skip + logs.length}
        </span>
        <button
          className={styles.pageBtn}
          onClick={() => setSkip(skip + PAGE_SIZE)}
          disabled={logs.length < PAGE_SIZE}
        >
          Next →
        </button>
      </div>

      {/* Slide-out Panel for Details */}
      <Drawer
        isOpen={!!expanded}
        onClose={() => setExpanded(null)}
        title="Document Lifecycle Details"
      >
        {expanded && (
          !details[expanded] ? (
            <div className={styles.detailLoading}>Loading unified audit trail...</div>
          ) : (
            <div className={styles.detailDrawerContent}>
              {/* Request Info */}
              <div className={styles.detailSection}>
                <div className={styles.sectionHeader}>
                  <FileText size={16} />
                  <p className={styles.detailLabel}>Source Details</p>
                </div>
                <div className={styles.infoRow}>
                  <span className={styles.infoKey}>Document ID</span>
                  <span className={styles.infoValue}>{details[expanded].id}</span>
                </div>
                {details[expanded].fileName && (
                  <div className={styles.infoRow}>
                    <span className={styles.infoKey}>File Name</span>
                    <span className={styles.infoValue}>{details[expanded].fileName}</span>
                  </div>
                )}
                {details[expanded].rawInput && (
                  <div className={styles.infoRow}>
                    <span className={styles.infoKey}>Raw Text Input</span>
                    <pre className={styles.infoValuePre}>{details[expanded].rawInput}</pre>
                  </div>
                )}
              </div>

              {/* Extraction Result */}
              <div className={styles.detailSection}>
                <div className={styles.sectionHeader}>
                  <CheckCircle2 size={16} />
                  <p className={styles.detailLabel}>Extraction Result</p>
                </div>
                {isInFlight(details[expanded].status) ? (
                  <ProgressPanel log={details[expanded]} />
                ) : details[expanded].status === 'NEEDS_REVIEW' && details[expanded].extractedJson && !Array.isArray(details[expanded].extractedJson) ? (
                  templateList ? (
                    <ReviewForm
                      key={details[expanded].id}
                      log={details[expanded]}
                      schema={templateList.find((t) => t.id === details[expanded!].templateId)?.schema ?? null}
                      onSaved={handleCorrected}
                    />
                  ) : (
                    <div className={styles.detailLoading}>Loading review form...</div>
                  )
                ) : details[expanded].extractedJson ? (
                  <div className={styles.jsonContainer}>
                    {typeof details[expanded].extractedJson === 'object' && !Array.isArray(details[expanded].extractedJson) ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {Object.entries(details[expanded].extractedJson as Record<string, unknown>).map(([key, value]) => {
                          const score = details[expanded].confidenceScores?.[key]
                          let color = 'var(--text-muted)'
                          let bg = 'var(--bg-subtle)'
                          if (score === 'High') { color = '#10b981'; bg = 'rgba(16, 185, 129, 0.1)' }
                          if (score === 'Medium') { color = '#f59e0b'; bg = 'rgba(245, 158, 11, 0.1)' }
                          if (score === 'Low') { color = '#ef4444'; bg = 'rgba(239, 68, 68, 0.1)' }
                          
                          return (
                            <div key={key} style={{ padding: '12px', background: 'var(--bg-card)', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                                <strong style={{ color: 'var(--text-color)' }}>{key}</strong>
                                {score && (
                                  <span style={{ fontSize: '12px', padding: '2px 8px', borderRadius: '12px', background: bg, color: color, fontWeight: 500 }}>
                                    {score} Confidence
                                  </span>
                                )}
                              </div>
                              <pre className={styles.json} style={{ margin: 0, border: 'none', background: 'var(--bg-body)' }}>
                                {JSON.stringify(value, null, 2)}
                              </pre>
                            </div>
                          )
                        })}
                      </div>
                    ) : (
                      <pre className={styles.json}>
                        {JSON.stringify(details[expanded].extractedJson, null, 2)}
                      </pre>
                    )}
                  </div>
                ) : details[expanded].status === 'FAILED' && describeFailure(details[expanded].validationErrors) ? (
                  <FailureDetails failure={describeFailure(details[expanded].validationErrors)!}>
                    <RetryAction log={details[expanded]} onRetried={handleRetried} />
                  </FailureDetails>
                ) : details[expanded].status === 'UNMATCHED' ? (
                  <div style={{ background: 'var(--bg-warning-subtle, rgba(245, 158, 11, 0.1))', border: '1px solid var(--border-warning, #f59e0b)', borderRadius: '8px', padding: '16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px', color: 'var(--text-warning, #d97706)' }}>
                      <FileQuestion size={18} />
                      <strong style={{ fontSize: '14px' }}>Template Not Found</strong>
                    </div>
                    <p style={{ fontSize: '13px', color: 'var(--text-color)', margin: 0, lineHeight: 1.5, opacity: 0.9 }}>
                      We analyzed this document but couldn't match it to any of your active templates. If this is a new type of document, try creating a new Template for it on the Templates page.
                    </p>
                  </div>
                ) : (
                  <p className={styles.emptyText}>No data extracted.</p>
                )}
              </div>
              
              {/* Webhook Deliveries */}
              <div className={styles.detailSection}>
                <div className={styles.sectionHeader}>
                  <Webhook size={16} />
                  <p className={styles.detailLabel}>Webhook Deliveries</p>
                </div>
                {details[expanded].webhookDeliveries && details[expanded].webhookDeliveries.length > 0 ? (
                  <ul className={styles.deliveryList}>
                    {details[expanded].webhookDeliveries.map(delivery => (
                      <li key={delivery.id} className={styles.deliveryItem}>
                        <div className={styles.deliveryHeader}>
                          {delivery.statusCode != null && delivery.statusCode >= 200 && delivery.statusCode < 300 ? (
                            <CheckCircle2 size={16} className={styles.iconSuccess} />
                          ) : (
                            <XCircle size={16} className={styles.iconError} />
                          )}
                          <span className={styles.mono}>HTTP {delivery.statusCode ?? 'ERR'}</span>
                          <span className={styles.monoMuted}>{delivery.durationMs}ms</span>
                          <span className={styles.dateMuted}>{new Date(delivery.createdAt).toLocaleString()}</span>
                        </div>
                        {delivery.responseBody && (
                          <pre className={styles.deliveryBody}>{delivery.responseBody}</pre>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className={styles.emptyText}>No webhook endpoints configured during this run.</p>
                )}
              </div>
            </div>
          )
        )}
      </Drawer>
    </div>

  )
}
