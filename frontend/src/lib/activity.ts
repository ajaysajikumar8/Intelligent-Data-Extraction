import type { ActivityCategory } from './types'

/** Readable title for each action the backend records (see backend `services/activity.py`). */
const ACTION_LABELS: Record<string, string> = {
  'auth.signed_up': 'Account created',
  'auth.email_verified': 'Email verified',
  'auth.login': 'Signed in',
  'auth.login_failed': 'Failed sign-in',
  'api_key.rotated': 'API key rotated',
  'inbound_secret.rotated': 'Inbound secret rotated',
  'gemini_key.set': 'Gemini key saved',
  'gemini_key.removed': 'Gemini key removed',
  'platform_fallback.enabled': 'Platform fallback on',
  'platform_fallback.disabled': 'Platform fallback off',
  'webhook.created': 'Webhook added',
  'webhook.updated': 'Webhook changed',
  'webhook.deleted': 'Webhook deleted',
  'webhook.auto_disabled': 'Webhook auto-disabled',
  'template.created': 'Template added',
  'template.updated': 'Template changed',
  'template.deleted': 'Template deleted',
  'document.corrected': 'Document corrected',
  'document.approved': 'Document approved',
  'document.retried': 'Extraction retried',
  'workspace.renamed': 'Workspace renamed',
}

export function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action
}

export const CATEGORY_OPTIONS: { value: ActivityCategory; label: string }[] = [
  { value: 'auth', label: 'Sign-in & account' },
  { value: 'keys', label: 'Keys & secrets' },
  { value: 'webhooks', label: 'Webhooks' },
  { value: 'templates', label: 'Templates' },
  { value: 'documents', label: 'Documents' },
  { value: 'workspace', label: 'Workspace' },
]
