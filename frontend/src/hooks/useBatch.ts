import { useContext } from 'react'
import { BatchContext } from '../contexts/BatchContext'

/** The dashboard-wide batch upload (see BatchContext). Must be used inside <BatchProvider>. */
export function useBatch() {
  const ctx = useContext(BatchContext)
  if (!ctx) throw new Error('useBatch must be used within a <BatchProvider>')
  return ctx
}
