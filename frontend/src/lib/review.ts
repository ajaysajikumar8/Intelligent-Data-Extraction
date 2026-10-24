/**
 * Helpers for the NEEDS_REVIEW screen: turn an extraction into editable text fields and back.
 * Values are edited as text, then parsed per field type, so a typo ("12,5") becomes a field
 * error instead of silently turning into null.
 */

export type FieldKind = 'string' | 'number' | 'integer' | 'boolean' | 'json'
export type Confidence = 'High' | 'Medium' | 'Low'

export interface ReviewField {
  key: string
  kind: FieldKind
  confidence: Confidence | null
}

const SCHEMA_KINDS: Record<string, FieldKind> = {
  string: 'string',
  number: 'number',
  integer: 'integer',
  boolean: 'boolean',
  array: 'json',
  object: 'json',
}

function inferKind(value: unknown): FieldKind {
  if (typeof value === 'number') return 'number'
  if (typeof value === 'boolean') return 'boolean'
  if (value !== null && typeof value === 'object') return 'json'
  return 'string'
}

/** Fields to review: template schema order first, then any extra keys the AI returned. */
export function buildFields(
  extracted: Record<string, unknown>,
  schema: Record<string, unknown> | null,
  scores: Record<string, Confidence> | null,
): ReviewField[] {
  const keys = [...Object.keys(schema ?? {}), ...Object.keys(extracted).filter((k) => !schema || !(k in schema))]
  const fields = keys.map((key): ReviewField => ({
    key,
    // Library templates describe some types in words ('array of objects with ...'): use the first word.
    kind: SCHEMA_KINDS[String(schema?.[key] ?? '').toLowerCase().split(/\s+/)[0]] ?? inferKind(extracted[key]),
    confidence: scores?.[key] ?? null,
  }))
  // Fields the AI was unsure about come first: that is where the user's attention is needed.
  const needsCheck = (f: ReviewField) => f.confidence === 'Low' || f.confidence === 'Medium'
  const rank = (f: ReviewField) => (f.confidence === 'Low' ? 0 : f.confidence === 'Medium' ? 1 : 2)
  return fields.every((f) => !needsCheck(f)) ? fields : [...fields].sort((a, b) => rank(a) - rank(b))
}

export function toDraft(value: unknown, kind: FieldKind): string {
  if (value === null || value === undefined) return ''
  if (kind === 'json') return JSON.stringify(value, null, 2)
  return String(value)
}

export type ParseResult = { ok: true; value: unknown } | { ok: false; error: string }

export function parseDraft(draft: string, kind: FieldKind): ParseResult {
  const text = draft.trim()
  if (text === '') return { ok: true, value: null }
  switch (kind) {
    case 'string':
      return { ok: true, value: draft }
    case 'number':
    case 'integer': {
      const n = Number(text)
      if (!Number.isFinite(n)) return { ok: false, error: 'Enter a number, for example 1250.50' }
      if (kind === 'integer' && !Number.isInteger(n)) return { ok: false, error: 'Enter a whole number' }
      return { ok: true, value: n }
    }
    case 'boolean':
      if (text === 'true' || text === 'false') return { ok: true, value: text === 'true' }
      return { ok: false, error: 'Choose yes or no' }
    case 'json':
      try {
        return { ok: true, value: JSON.parse(text) }
      } catch {
        return { ok: false, error: 'Enter valid JSON, for example ["a", "b"]' }
      }
  }
}

/** Parse every draft; returns the corrected object, or per-field errors if any value is invalid. */
export function parseAll(
  fields: ReviewField[],
  drafts: Record<string, string>,
): { ok: true; value: Record<string, unknown> } | { ok: false; errors: Record<string, string> } {
  const value: Record<string, unknown> = {}
  const errors: Record<string, string> = {}
  for (const f of fields) {
    const res = parseDraft(drafts[f.key] ?? '', f.kind)
    if (res.ok) value[f.key] = res.value
    else errors[f.key] = res.error
  }
  return Object.keys(errors).length ? { ok: false, errors } : { ok: true, value }
}
