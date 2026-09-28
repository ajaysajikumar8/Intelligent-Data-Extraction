/**
 * types.ts — TypeScript interfaces mirroring backend Pydantic schemas.
 * Keep in sync with backend/app/models/schemas.py.
 */

// ── Enums ──────────────────────────────────────────────────────────────────

export type Role = 'OWNER' | 'MEMBER'

export type Source = 'MANUAL' | 'API' | 'EMAIL' | 'WEBHOOK'

export type ExtractionStatus =
  | 'PENDING'
  | 'PROCESSING'
  | 'SUCCESS'
  | 'NEEDS_REVIEW'
  | 'FAILED'
  | 'UNMATCHED'

export type WebhookEventType = 'SUCCESS' | 'NEEDS_REVIEW' | 'FAILED' | 'UNMATCHED'

export type ThemeMode = 'system' | 'light' | 'dark'

// ── Auth / User ────────────────────────────────────────────────────────────

export interface UserResponse {
  id: string
  email: string
  name: string | null
  googleId: string | null
  avatarUrl: string | null
  workspaceId: string
  role: Role
  isActive: boolean
  createdAt: string
}

export interface WorkspaceResponse {
  id: string
  name: string
  slug: string
  apiKey: string
  inboundSecret: string
  planId: string
  createdAt: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: UserResponse
  workspace: WorkspaceResponse
}

// ── Templates ──────────────────────────────────────────────────────────────

export interface TemplateResponse {
  id: string
  workspaceId: string
  name: string
  description: string | null
  /** The extraction schema dict (serialized as `schema` from backend) */
  schema: Record<string, unknown>
  version: number
  isActive: boolean
  fieldCount: number
  createdAt: string
  updatedAt: string
}

export interface LibraryTemplateResponse {
  slug: string
  name: string
  description: string | null
  schema: Record<string, unknown>
  fieldCount: number
}

export interface TemplateCreate {
  name: string
  description?: string
  schema: Record<string, unknown>
}

export interface TemplateUpdate {
  name?: string
  description?: string
  schema?: Record<string, unknown>
  isActive?: boolean
}

// ── Document Logs ──────────────────────────────────────────────────────────

export interface DocumentLogResponse {
  id: string
  workspaceId: string
  templateId: string | null
  userId: string | null
  source: Source
  status: ExtractionStatus
  rawInput: string | null
  rawInputUrl: string | null
  fileName: string | null
  mimeType: string | null
  extractedJson: Record<string, unknown> | unknown[] | null
  confidenceScores: Record<string, 'High' | 'Medium' | 'Low'> | null
  validationErrors: unknown[] | Record<string, unknown> | null
  processingMs: number | null
  createdAt: string
}

// ── Workspace Members ──────────────────────────────────────────────────────

export interface WorkspaceMember {
  id: string
  email: string
  name: string | null
  role: Role
  isActive: boolean
  createdAt: string
}

// ── Pagination wrapper (future use) ───────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  skip: number
  limit: number
}

// ── API Error ──────────────────────────────────────────────────────────────

export interface ApiErrorDetail {
  detail: string | { msg: string; loc: string[] }[]
}

// ── Webhook types ──────────────────────────────────────────────────────────

export interface WebhookResponse {
  id: string
  workspaceId: string
  url: string
  secret: string
  description: string | null
  eventTypes: WebhookEventType[]
  templateIds: string[]
  isActive: boolean
  lastPingAt: string | null
  failureCount: number
  createdAt: string
  updatedAt: string
}

export interface WebhookCreate {
  url: string
  description?: string
  eventTypes?: WebhookEventType[]
  templateIds?: string[]
}

export interface WebhookUpdate {
  url?: string
  description?: string
  eventTypes?: WebhookEventType[]
  templateIds?: string[]
  isActive?: boolean
}

export interface WebhookDeliveryResponse {
  id: string
  webhookId: string
  documentLogId: string
  statusCode: number | null
  responseBody: string | null
  durationMs: number | null
  error: string | null
  createdAt: string
}

export interface InboundSecretResponse {
  inboundSecret: string
  inboundUrl: string
  message: string
}

export interface DocumentLogDetailResponse extends DocumentLogResponse {
  webhookDeliveries: WebhookDeliveryResponse[]
}
