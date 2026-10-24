/**
 * `DocumentLog.validationErrors` is a polymorphic JSON column. The backend
 * (`extraction_pipeline.py`, `failures.py`) writes one of these shapes when a
 * log is FAILED:
 *
 *   - `[{ field, message }, ...]`   — template-schema violations (Stage 3)
 *   - `{ error, code }`             — classified, user-safe failure (see `FailureCode`)
 *   - `{ error }`                   — legacy rows from before codes existed
 *   - `{ pipeline_error }`          — legacy rows holding a raw exception string
 *
 * `describeFailure` normalises these so the UI never has to guess. Legacy
 * `pipeline_error` text is deliberately NOT displayed: it can contain raw
 * provider errors.
 */

export interface FieldIssue {
  field: string
  message: string
}

export type FailureInfo =
  | { kind: 'fields'; issues: FieldIssue[] }
  | { kind: 'message'; title: string; message: string }
  | { kind: 'unknown'; raw: unknown }

/** Titles for backend `FailureCode`s. Unknown codes fall back to a generic title. */
const FAILURE_TITLES: Record<string, string> = {
  NO_AI_KEY: 'AI key required',
  AI_BUSY: 'AI service is busy',
  RATE_LIMITED: 'AI usage limit reached',
  AI_KEY_INVALID: 'AI key rejected',
  CONTENT_BLOCKED: 'No result from the AI',
  BAD_AI_OUTPUT: 'Unreadable AI response',
  UNPROCESSABLE: 'Document could not be read',
  TIMEOUT: 'Processing timed out',
  INTERRUPTED: 'Processing interrupted',
  INTERNAL: 'Processing failed',
}

const GENERIC_FAILURE_MESSAGE = 'Something went wrong while processing this document. Please try again.'

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
      const code = typeof validationErrors.code === 'string' ? validationErrors.code : undefined
      const title = code ? (FAILURE_TITLES[code] ?? 'Extraction failed') : 'Extraction could not start'
      return { kind: 'message', title, message: validationErrors.error }
    }
    if (typeof validationErrors.pipeline_error === 'string') {
      return { kind: 'message', title: 'Processing failed', message: GENERIC_FAILURE_MESSAGE }
    }
  }

  return { kind: 'unknown', raw: validationErrors }
}

/** Failure codes that a retry can fix. Keep in sync with `RETRYABLE_CODES` in backend `failures.py`. */
const RETRYABLE_CODES = new Set([
  'AI_BUSY', 'RATE_LIMITED', 'TIMEOUT', 'INTERRUPTED', 'BAD_AI_OUTPUT', 'NO_AI_KEY', 'AI_KEY_INVALID',
])

export type Retryability =
  | { kind: 'none' }
  | { kind: 'ok' }
  /** Would be retryable, but the original upload was not stored. */
  | { kind: 'needs-reupload'; reason: string }

export function retryability(log: {
  status: string
  validationErrors: unknown
  rawInput: string | null
  fileName: string | null
}): Retryability {
  if (log.status !== 'FAILED' || !isRecord(log.validationErrors)) return { kind: 'none' }
  const code = log.validationErrors.code
  if (typeof code !== 'string' || !RETRYABLE_CODES.has(code)) return { kind: 'none' }
  if (log.fileName || !log.rawInput?.trim()) {
    return { kind: 'needs-reupload', reason: "Uploaded files aren't stored, so please upload this document again." }
  }
  return { kind: 'ok' }
}
