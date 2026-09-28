/**
 * auth.ts — localStorage helpers for JWT + user session.
 * All token operations go through these functions — never access
 * localStorage directly elsewhere in the codebase.
 */

import type { TokenResponse, UserResponse, WorkspaceResponse } from './types'

const TOKEN_KEY = 'ide_access_token'
const USER_KEY = 'ide_user'
const WORKSPACE_KEY = 'ide_workspace'

// ── Token ──────────────────────────────────────────────────────────────────

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function removeToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

// ── User ───────────────────────────────────────────────────────────────────

export function getUser(): UserResponse | null {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? (JSON.parse(raw) as UserResponse) : null
  } catch {
    return null
  }
}

export function setUser(user: UserResponse): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function removeUser(): void {
  localStorage.removeItem(USER_KEY)
}

// ── Workspace ──────────────────────────────────────────────────────────────

export function getWorkspace(): WorkspaceResponse | null {
  try {
    const raw = localStorage.getItem(WORKSPACE_KEY)
    return raw ? (JSON.parse(raw) as WorkspaceResponse) : null
  } catch {
    return null
  }
}

export function setWorkspace(workspace: WorkspaceResponse): void {
  localStorage.setItem(WORKSPACE_KEY, JSON.stringify(workspace))
}

export function removeWorkspace(): void {
  localStorage.removeItem(WORKSPACE_KEY)
}

// ── Session ────────────────────────────────────────────────────────────────

/** Persist a full token response from login/signup. */
export function saveSession(data: TokenResponse): void {
  setToken(data.access_token)
  setUser(data.user)
  setWorkspace(data.workspace)
}

/** Clear all session data (logout). */
export function clearSession(): void {
  removeToken()
  removeUser()
  removeWorkspace()
}

/** True when a session token exists. */
export function isAuthenticated(): boolean {
  return getToken() !== null
}
