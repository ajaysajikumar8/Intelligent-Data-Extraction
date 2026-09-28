import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertTriangle, Check, Copy, ExternalLink, FileUp, GitMerge, Plus, Send, Sparkles, Upload, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { ingest, templates } from '../lib/api'
import type { DocumentLogResponse, TemplateResponse } from '../lib/types'
import { Button } from '../components/ui/Button'
import { Textarea } from '../components/ui/Input'
import { StatusBadge } from '../components/ui/Badge'
import styles from './Submit.module.css'

import { TemplateSelect } from '../components/ui/TemplateSelect'

export function Submit() {
  const navigate = useNavigate()
  const [tmplList, setTmplList] = useState<TemplateResponse[]>([])
  const [isLoadingTemplates, setIsLoadingTemplates] = useState(true)
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('')
  const [rawText, setRawText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<DocumentLogResponse | null>(null)
  const [copied, setCopied] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    templates.list()
      .then(setTmplList)
      .catch(() => {})
      .finally(() => setIsLoadingTemplates(false))
  }, [])

  const activeTemplates = tmplList.filter((t) => t.isActive)
  const selectedTemplate = activeTemplates.find((t) => t.id === selectedTemplateId)
  const matchedTemplate = result?.templateId ? tmplList.find((t) => t.id === result.templateId) : null

  const handleSubmit = async () => {
    const useText = rawText.trim()
    const useFile = file

    if (!useText && !useFile) {
      toast.error('Please provide at least a text body or an attached file.')
      return
    }

    setLoading(true); setResult(null); setCopied(false)
    try {
      const res = await ingest.submit({
        rawInput: useText || undefined,
        file: useFile || undefined,
        templateId: selectedTemplateId || undefined,
      })
      setResult(res)
      toast.success('Extraction complete!')
      setTimeout(() => {
        navigate('/logs')
      }, 700)
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Submission failed')
    } finally {
      setLoading(false)
    }
  }

  const handleCopyJson = () => {
    if (!result?.extractedJson) return
    navigator.clipboard.writeText(JSON.stringify(result.extractedJson, null, 2))
    setCopied(true)
    toast.success('Extracted JSON copied to clipboard!')
    setTimeout(() => setCopied(false), 2000)
  }

  const onFileDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped) setFile(dropped)
  }, [])

  const isSubmitDisabled = activeTemplates.length === 0 || loading

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Submit Document</h1>
        <p className={styles.sub}>Paste text, upload a file, or submit both together for AI extraction.</p>
      </div>

      {/* Empty State Banner when no active templates exist */}
      {!isLoadingTemplates && activeTemplates.length === 0 && (
        <div className={styles.emptyWarning}>
          <AlertTriangle size={24} className={styles.warningIcon} />
          <div className={styles.warningContent}>
            <h4 className={styles.warningTitle}>No Active Extraction Templates Found</h4>
            <p className={styles.warningDesc}>
              To extract structured JSON data, you need at least one active template defined for your workspace.
            </p>
          </div>
          <Link to="/templates" className={styles.createBtn}>
            <Plus size={16} /> Create Template
          </Link>
        </div>
      )}

      <div className={styles.layout}>
        <div className={styles.formCard}>
          {/* Template Selection Control */}
          <div className={styles.selectorCard}>
            <label className={styles.selectorLabel}>
              <Sparkles size={16} className={styles.sparkleIcon} />
              Extraction Schema Template
            </label>
            <TemplateSelect
              templates={tmplList}
              value={selectedTemplateId}
              onChange={setSelectedTemplateId}
              disabled={isLoadingTemplates ? false : activeTemplates.length === 0}
            />
            <p className={styles.selectorHint}>
              {selectedTemplateId === ''
                ? 'Gemini will automatically classify your document and select the best matching active template.'
                : `Forcing extraction strictly against template "${selectedTemplate?.name}".`}
            </p>
          </div>

          {/* Unified Input Panel */}
          <div className={styles.tabPanel}>
            <div className={styles.hybridNote}>
              <GitMerge size={14} />
              <span>
                You can provide text, a file, or both. Gemini will read both sources in a single pass if both are provided.
              </span>
            </div>

            <Textarea
              label="Document text (Optional)"
              id="submit-text"
              placeholder="Paste email body, document text, or any unstructured content here…"
              value={rawText}
              onChange={(e) => setRawText(e.target.value)}
              style={{ minHeight: 160 }}
            />
            
            <div className={styles.meta} style={{ marginTop: '-1rem' }}>
              <span className={styles.charCount}>{rawText.length} chars</span>
            </div>

            <label className={styles.hybridFileLabel}>Attached file (Optional)</label>
            <div
              className={[styles.dropzone, styles.dropzoneCompact, isDragging ? styles.dragOver : '', file ? styles.hasFile : ''].filter(Boolean).join(' ')}
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={onFileDrop}
              onClick={() => fileRef.current?.click()}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileRef.current?.click() } }}
              role="button"
              tabIndex={0}
              aria-label="Upload attachment"
            >
              {file ? (
                <div className={styles.fileInfo}>
                  <FileUp size={20} style={{ color: 'var(--color-accent)' }} />
                  <span className={styles.fileName}>{file.name}</span>
                  <span className={styles.fileSize}>{(file.size / 1024).toFixed(1)} KB</span>
                  <button
                    className={styles.removeFile}
                    onClick={(e) => { e.stopPropagation(); setFile(null) }}
                    aria-label="Remove attachment"
                  >
                    <X size={14} />
                  </button>
                </div>
              ) : (
                <>
                  <Upload size={24} style={{ color: 'var(--color-text-subtle)' }} />
                  <p className={styles.dropText}>Drop attachment here or click to browse</p>
                  <p className={styles.dropHint}>PDF, PNG, JPEG, WEBP · Max 20 MB</p>
                </>
              )}
            </div>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,.webp"
              style={{ display: 'none' }}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />

            <Button
              onClick={handleSubmit}
              loading={loading}
              disabled={isSubmitDisabled || (!rawText.trim() && !file)}
              size="lg"
              style={{ width: '100%', marginTop: '1rem' }}
            >
              <Send size={15} />
              Run extraction
            </Button>
          </div>
        </div>

        {/* Result panel */}
        {result && (
          <div className={styles.resultCard}>
            <div className={styles.resultHeader}>
              <div className={styles.resultTitleGroup}>
                <h3 className={styles.resultTitle}>Extraction Result</h3>
                <StatusBadge status={result.status} />
              </div>
              {result.extractedJson && (
                <Button variant="ghost" size="sm" onClick={handleCopyJson}>
                  {copied ? <Check size={14} color="var(--color-success)" /> : <Copy size={14} />}
                  {copied ? 'Copied' : 'Copy JSON'}
                </Button>
              )}
            </div>

            {/* Matched Template Info */}
            <div className={styles.templateMetaBadge}>
              <span className={styles.badgeLabel}>Matched Template:</span>
              <span className={styles.badgeValue}>
                {matchedTemplate ? `${matchedTemplate.name} (v${matchedTemplate.version})` : 'None / Unmatched'}
              </span>
            </div>

            {result.processingMs !== null && result.processingMs !== undefined && (
              <div className={styles.processingBadge}>
                ⚡ Processed in {result.processingMs} ms
              </div>
            )}

            {result.extractedJson ? (
              <pre className={styles.json}>
                {JSON.stringify(result.extractedJson, null, 2)}
              </pre>
            ) : result.validationErrors ? (
              <div className={styles.errorBox}>
                <p className={styles.errorHeader}>Validation / Pipeline Errors:</p>
                <pre className={styles.jsonError}>
                  {JSON.stringify(result.validationErrors, null, 2)}
                </pre>
              </div>
            ) : (
              <p className={styles.resultMeta}>No structured data extracted.</p>
            )}

            <div className={styles.resultFooter}>
              <Link to="/logs" className={styles.viewLogsLink}>
                View details in Extraction Logs <ExternalLink size={13} />
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
