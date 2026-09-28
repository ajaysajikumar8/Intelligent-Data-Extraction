import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import styles from './Drawer.module.css'

interface DrawerProps {
  isOpen: boolean
  onClose: () => void
  title?: string
  children: React.ReactNode
}

export function Drawer({ isOpen, onClose, title, children }: DrawerProps) {
  const [shouldRender, setShouldRender] = useState(isOpen)
  const panelRef = useRef<HTMLDivElement>(null)

  // Sync shouldRender with isOpen, but delay unmount for exit animation
  useEffect(() => {
    if (isOpen) {
      setShouldRender(true)
    } else {
      const timeoutId = setTimeout(() => {
        setShouldRender(false)
      }, 300) // Match CSS transition duration
      return () => clearTimeout(timeoutId)
    }
  }, [isOpen])

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  // Close on outside click
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
      onClose()
    }
  }

  // Prevent background scrolling when open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [isOpen])

  if (!shouldRender) return null

  return (
    <div 
      className={`${styles.backdrop} ${isOpen ? styles.backdropOpen : styles.backdropClosed}`} 
      onClick={handleBackdropClick}
    >
      <div
        className={`${styles.panel} ${isOpen ? styles.panelOpen : styles.panelClosed}`}
        ref={panelRef}
      >
        <div className={styles.header}>
          {title && <h2 className={styles.title}>{title}</h2>}
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close panel">
            <X size={20} />
          </button>
        </div>
        <div className={styles.content}>
          {children}
        </div>
      </div>
    </div>
  )
}
