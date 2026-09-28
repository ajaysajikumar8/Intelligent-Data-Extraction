import React, { createContext, useContext, useEffect, useRef, useState, ReactNode } from 'react'
import { X, ChevronLeft } from 'lucide-react'
import styles from './StackedDrawer.module.css'

export type DrawerScreen = {
  id: string
  title?: string
  content: ReactNode
}

type StackedDrawerContextType = {
  push: (screen: DrawerScreen) => void
  pop: () => void
  reset: () => void
}

const StackedDrawerContext = createContext<StackedDrawerContextType | null>(null)

export const useStackedDrawer = () => {
  const ctx = useContext(StackedDrawerContext)
  if (!ctx) throw new Error('useStackedDrawer must be used within StackedDrawer')
  return ctx
}

interface StackedDrawerProps {
  isOpen: boolean
  onClose: () => void
  rootScreen: DrawerScreen
}

export function StackedDrawer({ isOpen, onClose, rootScreen }: StackedDrawerProps) {
  const [shouldRender, setShouldRender] = useState(isOpen)
  const panelRef = useRef<HTMLDivElement>(null)
  
  // activeStack ONLY holds the pushed screens.
  const [activeStack, setActiveStack] = useState<DrawerScreen[]>([])
  // renderedStack allows us to keep popped screens in the DOM briefly for exit animations
  const [renderedStack, setRenderedStack] = useState<DrawerScreen[]>([])

  // Sync shouldRender with isOpen, but delay unmount for exit animation
  useEffect(() => {
    if (isOpen) {
      setShouldRender(true)
    } else {
      const timeoutId = setTimeout(() => {
        setShouldRender(false)
        setActiveStack([])
        setRenderedStack([])
      }, 300)
      return () => clearTimeout(timeoutId)
    }
  }, [isOpen])

  // Handle active stack changes for exit animations
  useEffect(() => {
    if (activeStack.length < renderedStack.length) {
      // A screen was popped. Keep it in renderedStack for 300ms to animate it sliding right
      const timeoutId = setTimeout(() => {
        setRenderedStack(activeStack)
      }, 300)
      return () => clearTimeout(timeoutId)
    } else {
      // Pushing a new screen. Mount it immediately
      setRenderedStack(activeStack)
    }
  }, [activeStack])

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        if (activeStack.length > 0) {
          pop()
        } else {
          onClose()
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose, activeStack.length])

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

  const push = (screen: DrawerScreen) => {
    setActiveStack(prev => [...prev, screen])
  }

  const pop = () => {
    setActiveStack(prev => prev.length > 0 ? prev.slice(0, -1) : prev)
  }

  const reset = () => {
    setActiveStack([])
  }

  if (!shouldRender) return null

  // Compose the full stacks by prepending the rootScreen
  const fullActiveStack = [rootScreen, ...activeStack]
  const fullRenderedStack = [rootScreen, ...renderedStack]

  return (
    <StackedDrawerContext.Provider value={{ push, pop, reset }}>
      <div 
        className={`${styles.backdrop} ${isOpen ? styles.backdropOpen : styles.backdropClosed}`} 
        onClick={handleBackdropClick}
      >
        <div
          className={`${styles.panel} ${isOpen ? styles.panelOpen : styles.panelClosed}`}
          ref={panelRef}
        >
          {fullRenderedStack.map((screen, index) => {
            // Determine animation class based on fullActiveStack (logical state)
            const isActive = index === fullActiveStack.length - 1
            const isPrevious = index < fullActiveStack.length - 1
            const isPopped = index > fullActiveStack.length - 1 // Screen is animating out

            let screenClass = styles.screenNext
            if (isActive) screenClass = styles.screenActive
            if (isPrevious) screenClass = styles.screenPrevious
            if (isPopped) screenClass = styles.screenNext // Slides back to the right

            return (
              <div key={screen.id} className={`${styles.screen} ${screenClass}`}>
                <div className={styles.header}>
                  {index > 0 && (
                    <button className={styles.backBtn} onClick={pop} aria-label="Go back">
                      <ChevronLeft size={20} /> Back
                    </button>
                  )}
                  {screen.title && <h2 className={styles.title}>{screen.title}</h2>}
                  <button className={styles.closeBtn} onClick={onClose} aria-label="Close panel">
                    <X size={20} />
                  </button>
                </div>
                <div className={styles.content}>
                  {screen.content}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </StackedDrawerContext.Provider>
  )
}
