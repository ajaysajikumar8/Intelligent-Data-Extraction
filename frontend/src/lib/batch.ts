/** Client-side limits for uploads. The server re-validates type and size on every file. */
export const MAX_FILE_BYTES = 20 * 1024 * 1024
export const MAX_BATCH_FILES = 20
export const ACCEPTED_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg', '.webp']

export interface PickedFiles {
  accepted: File[]
  /** Human-readable reasons for files that were left out. */
  skipped: string[]
}

/**
 * Merge newly picked files into the current selection: drops unsupported types,
 * oversize files and duplicates, and stops at MAX_BATCH_FILES.
 */
export function mergeFiles(current: File[], incoming: File[]): PickedFiles {
  const accepted = [...current]
  const skipped: string[] = []
  const seen = new Set(current.map((f) => `${f.name}:${f.size}:${f.lastModified}`))

  for (const file of incoming) {
    const id = `${file.name}:${file.size}:${file.lastModified}`
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
    if (seen.has(id)) continue
    if (!ACCEPTED_EXTENSIONS.includes(ext)) skipped.push(`${file.name}: unsupported file type`)
    else if (file.size > MAX_FILE_BYTES) skipped.push(`${file.name}: larger than 20 MB`)
    else if (accepted.length >= MAX_BATCH_FILES) skipped.push(`${file.name}: batch limit of ${MAX_BATCH_FILES} files reached`)
    else { accepted.push(file); seen.add(id) }
  }
  return { accepted, skipped }
}
