/**
 * api.ts — Typed fetch client for the FastAPI backend.
 *
 * All API calls go through `request()`. It:
 *   - Reads the base URL from import.meta.env.VITE_API_BASE_URL
 *   - Injects the Authorization: Bearer <token> header automatically
 *   - Throws ApiError (with status + detail) on non-2xx responses
 *   - On 401 → clears session and redirects to /login
 */

import toast from 'react-hot-toast'
import { clearSession, getToken } from './auth'
import type {
  DocumentLogDetailResponse,
  DocumentLogResponse,
  ExtractionStatus,
  InboundSecretResponse,
  LibraryTemplateResponse,
  Source,
  TemplateCreate,
  TemplateResponse,
  TemplateUpdate,
  TokenResponse,
  WebhookCreate,
  WebhookDeliveryResponse,
  WebhookResponse,
  WebhookUpdate,
  WorkspaceMember,
  WorkspaceResponse,
} from './types'

// ── Error class ────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail)
    this.name = 'ApiError'
  }
}

let isRedirecting = false

// ── Core request ───────────────────────────────────────────────────────────

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken()
  const headers = new Headers(options.headers)

  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  // Only set Content-Type for JSON — don't set it for FormData (browser handles boundary)
  if (!(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${BASE_URL}${path}`, { ...options, headers })

  if (response.status === 401) {
    if (!isRedirecting && window.location.pathname !== '/login') {
      isRedirecting = true
      toast.error('Session expired. Please log in again.', { duration: 3000 })
      setTimeout(() => {
        clearSession()
        window.location.href = '/login'
      }, 2000)
    }
    throw new ApiError(401, 'Session expired. Please log in again.')
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const body = await response.json() as { detail?: string | { msg: string }[] }
      if (typeof body.detail === 'string') {
        detail = body.detail
      } else if (Array.isArray(body.detail)) {
        detail = body.detail.map((d) => d.msg).join(', ')
      }
    } catch {
      // ignore parse errors
    }
    throw new ApiError(response.status, detail)
  }

  // 204 No Content
  if (response.status === 204) return undefined as T

  return response.json() as Promise<T>
}

// ── Auth endpoints ─────────────────────────────────────────────────────────

export const auth = {
  signup: (payload: {
    email: string
    password: string
    name?: string
    workspaceName?: string
  }) =>
    request<TokenResponse>('/auth/signup', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  login: (email: string, password: string) =>
    request<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<TokenResponse>('/auth/me'),
}

// ── Workspace endpoints ────────────────────────────────────────────────────

export const workspaces = {
  get: () => request<WorkspaceResponse>('/workspaces/current'),

  update: (name: string) =>
    request<WorkspaceResponse>('/workspaces/current', {
      method: 'PUT',
      body: JSON.stringify({ name }),
    }),

  rotateApiKey: () =>
    request<{ apiKey: string; message: string }>('/workspaces/current/api-key/rotate', {
      method: 'POST',
    }),

  listMembers: () => request<WorkspaceMember[]>('/workspaces/current/members'),
}

// ── Template endpoints ─────────────────────────────────────────────────────

export const templates = {
  getLibrary: () => request<LibraryTemplateResponse[]>('/templates/library'),

  duplicateFromLibrary: (slug: string) =>
    request<TemplateResponse>(`/templates/library/${slug}/duplicate`, { method: 'POST' }),

  list: () => request<TemplateResponse[]>('/templates/'),

  get: (id: string) => request<TemplateResponse>(`/templates/${id}`),

  create: (payload: TemplateCreate) =>
    request<TemplateResponse>('/templates/', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  update: (id: string, payload: TemplateUpdate) =>
    request<TemplateResponse>(`/templates/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  delete: (id: string) =>
    request<void>(`/templates/${id}`, { method: 'DELETE' }),
}

// ── Ingest endpoints ───────────────────────────────────────────────────────

export const ingest = {
  /**
   * Submit a document for AI extraction.
   *
   * Accepts any combination of rawInput (text) and/or file.
   * At least one must be provided. When both are provided, Gemini
   * processes them together in a single multimodal call (hybrid mode).
   *
   * source identifies the ingestion channel:
   *   • 'MANUAL'  — human user on the dashboard (default)
   *   • 'API'     — developer calling with an API key
   *   • 'EMAIL'   — automated email forwarding pipeline
   *   • 'WEBHOOK' — inbound trigger from Zapier, Make.com, etc.
   */
  submit: (params: {
    rawInput?: string
    file?: File
    templateId?: string
    source?: Source
  }) => {
    const form = new FormData()
    if (params.rawInput) form.append('rawInput', params.rawInput)
    if (params.file) form.append('file', params.file)
    form.append('source', params.source ?? 'MANUAL')
    if (params.templateId) form.append('templateId', params.templateId)
    return request<DocumentLogResponse>('/ingest/', {
      method: 'POST',
      body: form,
    })
  },

  /** List document logs (paginated). */
  list: (params?: {
    skip?: number
    limit?: number
    status?: ExtractionStatus
    source?: Source
  }) => {
    const qs = new URLSearchParams()
    if (params?.skip !== undefined) qs.set('skip', String(params.skip))
    if (params?.limit !== undefined) qs.set('limit', String(params.limit))
    if (params?.status) qs.set('status', params.status)
    if (params?.source) qs.set('source', params.source)
    const query = qs.toString()
    return request<DocumentLogResponse[]>(`/ingest/${query ? `?${query}` : ''}`)
  },
}

// ── Webhooks ───────────────────────────────────────────────────────

export const webhooks = {
  /** List all outbound webhook endpoints for the workspace. */
  list: () => request<WebhookResponse[]>('/webhooks/'),

  /** Get a single outbound webhook by ID. */
  get: (id: string) => request<WebhookResponse>(`/webhooks/${id}`),

  /** Register a new outbound webhook endpoint. */
  create: (payload: WebhookCreate) =>
    request<WebhookResponse>('/webhooks/', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  /** Update a webhook's URL, description, filters, or active state. */
  update: (id: string, payload: WebhookUpdate) =>
    request<WebhookResponse>(`/webhooks/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  /** Delete a webhook and all its delivery history. */
  delete: (id: string) =>
    request<void>(`/webhooks/${id}`, { method: 'DELETE' }),

  /** Send a test ping to the webhook URL. */
  ping: (id: string) =>
    request<{ success: boolean; statusCode: number | null; responseBody: string; url: string }>(
      `/webhooks/${id}/ping`,
      { method: 'POST' },
    ),

  /** List the last 50 delivery attempts for a webhook. */
  deliveries: (id: string) =>
    request<WebhookDeliveryResponse[]>(`/webhooks/${id}/deliveries`),

  // ── Inbound URL management ─────────────────────────────────────────

  /** Get the workspace's inbound webhook URL. */
  getInboundUrl: () => request<InboundSecretResponse>('/webhooks/inbound'),

  /** Rotate the inbound secret, invalidating the old URL immediately. */
  rotateInboundSecret: () =>
    request<InboundSecretResponse>('/webhooks/inbound/rotate', { method: 'POST' }),
}

// ── Audit Logs ──────────────────────────────────────────────────────

export const logs = {
  /**
   * Get the full audit trail for a single document extraction.
   * Includes extraction result, template info, and all webhook delivery attempts.
   */
  get: (documentId: string) =>
    request<DocumentLogDetailResponse>(`/logs/${documentId}`),

  /**
   * Submit human corrections for an extraction.
   * This updates the log status to SUCCESS, stores the correction for prompt injection,
   * and fires the final outbound webhook.
   */
  correct: (documentId: string, correctedJson: Record<string, unknown>) =>
    request<DocumentLogDetailResponse>(`/logs/${documentId}/correct`, {
      method: 'POST',
      body: JSON.stringify({ correctedJson }),
    }),
}
