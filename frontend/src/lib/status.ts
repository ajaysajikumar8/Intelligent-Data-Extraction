import type { ApiKeySource, ExtractionStatus } from './types'

/** Statuses where the extraction is queued or running and the result is not final yet. */
export function isInFlight(status: ExtractionStatus): boolean {
  return status === 'PENDING' || status === 'PROCESSING'
}

/** Plain-language label for whose Gemini key paid for an extraction. */
export const KEY_SOURCE_LABELS: Record<ApiKeySource, string> = {
  WORKSPACE: 'Your own Gemini key',
  PLATFORM: 'Platform key (fallback on your plan)',
  TRIAL_CREDIT: 'Platform key (free trial credit)',
  WORKSPACE_THEN_PLATFORM: 'Your key, then the platform key (your key hit its limit)',
}
