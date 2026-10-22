import type { ExtractionStatus } from './types'

/** Statuses where the extraction is queued or running and the result is not final yet. */
export function isInFlight(status: ExtractionStatus): boolean {
  return status === 'PENDING' || status === 'PROCESSING'
}
