import { useMemo, useState } from 'react'
import { AlertTriangle, Check, RotateCcw } from 'lucide-react'
import toast from 'react-hot-toast'
import { ApiError, logs } from '../lib/api'
import { buildFields, parseAll, toDraft, type Confidence } from '../lib/review'
import type { DocumentLogDetailResponse } from '../lib/types'
import { Button } from './ui/Button'
import styles from './ReviewForm.module.css'

interface ReviewFormProps {
  log: DocumentLogDetailResponse
  /** Extraction schema of the matched template (field -> type), if it could be loaded. */
  schema: Record<string, unknown> | null
  onSaved: (updated: DocumentLogDetailResponse) => void
}

const CONFIDENCE_LABEL: Record<Confidence, string> = {
  Low: 'Low confidence: please check',
  Medium: 'Medium confidence: worth a look',
  High: 'High confidence',
}

/**
 * Review screen for a NEEDS_REVIEW document: one labelled input per extracted field, the
 * AI's least-sure fields first. "Approve" confirms the values as they are; editing any field
 * turns it into "Save corrections". Either way the document becomes SUCCESS.
 */
export function ReviewForm({ log, schema, onSaved }: ReviewFormProps) {
  const extracted = useMemo(
    () => (log.extractedJson && !Array.isArray(log.extractedJson) ? log.extractedJson : {}) as Record<string, unknown>,
    [log.extractedJson],
  )
  const fields = useMemo(
    () => buildFields(extracted, schema, log.confidenceScores),
    [extracted, schema, log.confidenceScores],
  )
  const initial = useMemo(
    () => Object.fromEntries(fields.map((f) => [f.key, toDraft(extracted[f.key], f.kind)])),
    [fields, extracted],
  )

  const [drafts, setDrafts] = useState<Record<string, string>>(initial)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)

  const dirty = fields.some((f) => drafts[f.key] !== initial[f.key])
  const flagged = fields.filter((f) => f.confidence === 'Low' || f.confidence === 'Medium').length

  const setDraft = (key: string, value: string) => {
    setDrafts((d) => ({ ...d, [key]: value }))
    setErrors((e) => (key in e ? Object.fromEntries(Object.entries(e).filter(([k]) => k !== key)) : e))
  }

  const submit = async () => {
    const parsed = parseAll(fields, drafts)
    if (!parsed.ok) { setErrors(parsed.errors); return }

    setSaving(true)
    try {
      // Unchanged fields go back exactly as extracted, so approving never alters the data.
      const value = dirty ? parsed.value : extracted
      onSaved(await logs.correct(log.id, value))
      toast.success(dirty ? 'Corrections saved' : 'Extraction approved')
    } catch (e) {
      if (e instanceof ApiError && Object.keys(e.fieldErrors).length > 0) {
        setErrors(e.fieldErrors)
        toast.error('Some values do not match the template. Check the highlighted fields.')
      } else {
        toast.error(e instanceof Error ? e.message : 'Could not save')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={styles.form}>
      <p className={styles.intro}>
        <AlertTriangle size={14} aria-hidden="true" />
        {flagged > 0
          ? `${flagged} field${flagged === 1 ? '' : 's'} need${flagged === 1 ? 's' : ''} your check. Fix anything that is wrong, then approve.`
          : 'Check the values, fix anything that is wrong, then approve.'}
      </p>

      {fields.map((f) => {
        const id = `review-${log.id}-${f.key}`
        const error = errors[f.key]
        const flaggedField = f.confidence === 'Low' || f.confidence === 'Medium'
        return (
          <div key={f.key} className={[styles.field, flaggedField ? styles.flagged : ''].filter(Boolean).join(' ')}>
            <div className={styles.fieldHead}>
              <label htmlFor={id} className={styles.label}>{f.key}</label>
              {f.confidence && (
                <span className={styles.badge} data-level={f.confidence}>{CONFIDENCE_LABEL[f.confidence]}</span>
              )}
            </div>

            {f.kind === 'boolean' ? (
              <select
                id={id}
                className={styles.control}
                value={drafts[f.key]}
                onChange={(e) => setDraft(f.key, e.target.value)}
                aria-invalid={!!error}
              >
                <option value="">Not found</option>
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
            ) : f.kind === 'json' ? (
              <textarea
                id={id}
                className={`${styles.control} ${styles.mono}`}
                rows={4}
                value={drafts[f.key]}
                onChange={(e) => setDraft(f.key, e.target.value)}
                aria-invalid={!!error}
                spellCheck={false}
              />
            ) : (
              <input
                id={id}
                className={styles.control}
                type="text"
                inputMode={f.kind === 'string' ? 'text' : 'decimal'}
                value={drafts[f.key]}
                placeholder="Not found"
                onChange={(e) => setDraft(f.key, e.target.value)}
                aria-invalid={!!error}
              />
            )}
            {error && <span className={styles.error} role="alert">{error}</span>}
          </div>
        )
      })}

      <div className={styles.actions}>
        {dirty && (
          <Button variant="ghost" onClick={() => { setDrafts(initial); setErrors({}) }} disabled={saving}>
            <RotateCcw size={14} /> Undo changes
          </Button>
        )}
        <Button onClick={submit} loading={saving}>
          <Check size={15} /> {dirty ? 'Save corrections' : 'Approve as is'}
        </Button>
      </div>
    </div>
  )
}
