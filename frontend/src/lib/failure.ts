/**
 * `DocumentLog.validationErrors` is a polymorphic JSON column. The backend
 * (`extraction_pipeline.py`) writes one of three shapes when a log is FAILED:
 *
 *   - `[{ field, message }, ...]`  — template-schema violations (Stage 3)
 *   - `{ error: string }`          — pre-flight failure, e.g. no AI key configured
 *   - `{ pipeline_error: string }` — unexpected exception during processing
 *
 * `describeFailure` normalises these so the UI never has to guess.
 */

export interface FieldIssue {
  field: string
  message: string
}

export type FailureInfo =
  | { kind: 'fields'; issues: FieldIssue[] }
  | { kind: 'message'; title: string; message: string }
  | { kind: 'unknown'; raw: unknown }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function describeFailure(validationErrors: unknown): FailureInfo | null {
  if (validationErrors == null) return null

  if (Array.isArray(validationErrors)) {
    const issues = validationErrors.map((item): FieldIssue => {
      const rec = isRecord(item) ? item : {}
      return {
        field: typeof rec.field === 'string' ? rec.field : 'unknown',
        message: typeof rec.message === 'string' ? rec.message : JSON.stringify(item),
      }
    })
    return issues.length ? { kind: 'fields', issues } : null
  }

  if (isRecord(validationErrors)) {
    if (typeof validationErrors.error === 'string') {
      return { kind: 'message', title: 'Extraction could not start', message: validationErrors.error }
    }
    if (typeof validationErrors.pipeline_error === 'string') {
      return { kind: 'message', title: 'Processing error', message: validationErrors.pipeline_error }
    }
  }

  return { kind: 'unknown', raw: validationErrors }
}
