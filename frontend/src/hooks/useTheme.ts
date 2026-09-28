/**
 * useTheme.ts — Typed hook for consuming ThemeContext.
 *
 * Only components that need to READ or SET the theme mode use this hook
 * (e.g., ThemeSelector in Settings, or a theme toggle button).
 * All other components just use CSS variables — no JS needed.
 */

import { useContext } from 'react'
import { ThemeContext } from '../contexts/ThemeContext'

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) {
    throw new Error('useTheme must be used within a <ThemeProvider>')
  }
  return ctx
}
