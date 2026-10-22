import type { DocumentLogResponse } from './types'

function download(content: string, mimeType: string, filename: string) {
  const url = URL.createObjectURL(new Blob([content], { type: mimeType }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

const defaultName = () => `extractions_export_${new Date().toISOString()}`

/**
 * Extracted values come from untrusted documents. A cell starting with
 * = + - @ would run as a formula when the CSV is opened in a spreadsheet,
 * so prefix it with a quote. Plain numbers (e.g. -12.50) are left alone.
 */
function csvCell(value: string): string {
  const looksLikeFormula = /^[=+\-@\t\r]/.test(value) && !/^-?\d+(\.\d+)?$/.test(value)
  const safe = looksLikeFormula ? `'${value}` : value
  return `"${safe.replace(/"/g, '""')}"`
}

export function exportLogsAsJson(logs: DocumentLogResponse[], name = defaultName()) {
  download(JSON.stringify(logs, null, 2), 'application/json', `${name}.json`)
}

export function exportLogsAsCsv(logs: DocumentLogResponse[], name = defaultName()) {
  if (logs.length === 0) return

  const headers = new Set<string>(['id', 'status', 'source', 'createdAt', 'fileName'])

  const flatData = logs.map((log) => {
    const base: Record<string, string> = {
      id: log.id,
      createdAt: new Date(log.createdAt).toISOString(),
      status: log.status,
      source: log.source,
      fileName: log.fileName || '',
    }
    if (log.extractedJson) {
      let json: unknown = log.extractedJson
      if (Array.isArray(json) && json.length > 0) {
        json = json[0] // take first item if array
      }
      if (typeof json === 'object' && json !== null) {
        for (const [k, v] of Object.entries(json)) {
          headers.add(`data.${k}`)
          base[`data.${k}`] = typeof v === 'object' ? JSON.stringify(v) : String(v)
        }
      }
    }
    return base
  })

  const headerRow = Array.from(headers)
  const rows = [
    headerRow.join(','),
    ...flatData.map((d) => headerRow.map((h) => csvCell(d[h] || '')).join(',')),
  ]

  download(rows.join('\n'), 'text/csv', `${name}.csv`)
}
