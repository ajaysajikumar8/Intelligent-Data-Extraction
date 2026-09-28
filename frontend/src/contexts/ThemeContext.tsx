/**
 * ThemeContext.tsx — Theme management with system preference detection.
 *
 * Three modes:
 *   'system'  — follows OS prefers-color-scheme (default, auto-updates on change)
 *   'light'   — forced light regardless of OS
 *   'dark'    — forced dark regardless of OS
 *
 * Usage:
 *   Wrap your app in <ThemeProvider>. Consume via useTheme() hook.
 *   Only the ThemeSelector widget needs this context — all other
 *   components just reference CSS variables, no JS needed.
 */

import {
  createContext,
  useCallback,
  useEffect,
  useState,
} from 'react'
import type { ReactNode } from 'react'
import type { ThemeMode } from '../lib/types'

// ── Types ──────────────────────────────────────────────────────────────────

interface ThemeContextValue {
  /** What the user explicitly chose (or 'system' default). */
  themeMode: ThemeMode
  /** What is actually rendered right now ('light' | 'dark'). */
  resolvedTheme: 'light' | 'dark'
  /** Update the theme mode and persist to localStorage. */
  setThemeMode: (mode: ThemeMode) => void
}

// ── Context ────────────────────────────────────────────────────────────────

const ThemeContext = createContext<ThemeContextValue | null>(null)

// ── Helpers ────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'theme-mode'
const ATTR = 'data-theme'

function getSystemTheme(): 'light' | 'dark' {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light'
}

function resolve(mode: ThemeMode): 'light' | 'dark' {
  return mode === 'system' ? getSystemTheme() : mode
}

function applyTheme(resolved: 'light' | 'dark'): void {
  document.documentElement.setAttribute(ATTR, resolved)
}

// ── Provider ───────────────────────────────────────────────────────────────

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [themeMode, setThemeModeState] = useState<ThemeMode>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored === 'light' || stored === 'dark' || stored === 'system') {
        return stored
      }
    } catch {
      // ignore
    }
    return 'system'
  })

  const [resolvedTheme, setResolvedTheme] = useState<'light' | 'dark'>(() =>
    resolve(themeMode),
  )

  // Apply theme to DOM and update state
  const applyMode = useCallback((mode: ThemeMode) => {
    const resolved = resolve(mode)
    applyTheme(resolved)
    setResolvedTheme(resolved)
  }, [])

  // On mode change: persist + apply
  const setThemeMode = useCallback(
    (mode: ThemeMode) => {
      try {
        localStorage.setItem(STORAGE_KEY, mode)
      } catch {
        // ignore
      }
      setThemeModeState(mode)
      applyMode(mode)
    },
    [applyMode],
  )

  // On mount: apply initial theme (may already be set by FOUC script, but
  // we sync React state with the actual resolved value)
  useEffect(() => {
    applyMode(themeMode)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Watch OS preference changes when in 'system' mode
  useEffect(() => {
    if (themeMode !== 'system') return

    const mql = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = () => {
      const resolved = getSystemTheme()
      applyTheme(resolved)
      setResolvedTheme(resolved)
    }

    mql.addEventListener('change', handler)
    return () => mql.removeEventListener('change', handler)
  }, [themeMode])

  return (
    <ThemeContext.Provider value={{ themeMode, resolvedTheme, setThemeMode }}>
      {children}
    </ThemeContext.Provider>
  )
}

// ── Export context for hook ────────────────────────────────────────────────

export { ThemeContext }
