import { useEffect, useRef, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Menu, Zap } from 'lucide-react'
import { Sidebar } from './Sidebar'
import { VerifyEmailBanner } from './VerifyEmailBanner'
import { BatchProvider } from '../../contexts/BatchContext'
import { useMediaQuery } from '../../hooks/useMediaQuery'
import { APP_NAME } from '../../lib/brand'
import styles from './DashboardLayout.module.css'

/**
 * DashboardLayout — shell for all authenticated pages.
 * Desktop: fixed sidebar left + scrollable main content right.
 * Mobile (<=768px): sidebar becomes an off-canvas drawer opened from the top bar.
 */
export function DashboardLayout() {
  const isMobile = useMediaQuery('(max-width: 768px)')
  const [navOpen, setNavOpen] = useState(false)
  const menuBtnRef = useRef<HTMLButtonElement>(null)
  const { pathname } = useLocation()

  // Close the drawer on navigation, and when the viewport grows past the breakpoint.
  useEffect(() => { setNavOpen(false) }, [pathname, isMobile])

  const closeNav = () => {
    setNavOpen(false)
    menuBtnRef.current?.focus()
  }

  return (
    <BatchProvider>
      <div className={styles.layout}>
        {isMobile && (
          <header className={styles.topbar}>
            <button
              ref={menuBtnRef}
              className={styles.menuBtn}
              onClick={() => setNavOpen(true)}
              aria-label="Open navigation menu"
              aria-expanded={navOpen}
              aria-controls="app-sidebar"
            >
              <Menu size={20} />
            </button>
            <div className={styles.topbarBrand}>
              <span className={styles.topbarLogo}><Zap size={14} /></span>
              <span className={styles.topbarName}>{APP_NAME}</span>
            </div>
          </header>
        )}

        {isMobile && navOpen && (
          <div className={styles.scrim} onClick={closeNav} aria-hidden="true" />
        )}

        <Sidebar id="app-sidebar" drawer={isMobile} open={navOpen} onClose={closeNav} />

        <main className={styles.main}>
          <VerifyEmailBanner />
          <div className={styles.content}>
            <Outlet />
          </div>
        </main>
      </div>
    </BatchProvider>
  )
}
