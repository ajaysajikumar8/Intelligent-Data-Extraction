import type { ExtractionProgress, ExtractionStatus } from './types'

/** The three user-visible steps of an extraction. */
export const PROGRESS_STEPS = ['Queued', 'Reading', 'Extracting'] as const

export interface ProgressView {
  headline: string
  detail: string
  /** Index into PROGRESS_STEPS of the step currently running. */
  step: 0 | 1 | 2
  retrying: boolean
}

const stageStep = (stage: ExtractionProgress['stage'] | undefined): 1 | 2 => (stage === 'EXTRACTING' ? 2 : 1)

/** Plain-language description of where an in-flight document is. */
export function describeProgress(status: ExtractionStatus, progress: ExtractionProgress | null): ProgressView {
  if (status === 'PENDING') {
    return { headline: 'Queued', detail: 'Waiting for a free processing slot.', step: 0, retrying: false }
  }
  if (progress?.retryReason) {
    return {
      headline: 'The AI service is busy',
      detail: `Retrying automatically (attempt ${progress.attempt} of ${progress.maxAttempts}). No action needed.`,
      step: stageStep(progress.stage),
      retrying: true,
    }
  }
  if (progress?.stage === 'EXTRACTING') {
    return { headline: 'Extracting fields', detail: 'Pulling the data out of your document.', step: 2, retrying: false }
  }
  return { headline: 'Reading your document', detail: 'Working out which template fits.', step: 1, retrying: false }
}

/** Short label for a table row, or null when the status badge says enough. */
export function progressHint(status: ExtractionStatus, progress: ExtractionProgress | null): string | null {
  if (status === 'PENDING') return 'Queued'
  if (status !== 'PROCESSING') return null
  if (progress?.retryReason) return `Retrying ${progress.attempt}/${progress.maxAttempts}`
  return progress?.stage === 'EXTRACTING' ? 'Extracting' : 'Reading'
}

export function formatElapsed(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds))
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`
}
