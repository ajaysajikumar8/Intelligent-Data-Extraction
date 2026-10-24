import { useEffect, useRef, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Menu, Zap } from 'lucide-react'
import { Sidebar } from './Sidebar'
import { VerifyEmailBanner } from './VerifyEmailBanner'
import { useMediaQuery } from '../../hooks/useMediaQuery'
import { useFinishedDocs } from '../../hooks/useFinishedDocs'
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
  const finishedDocs = useFinishedDocs(pathname.startsWith('/logs'))

  // Close the drawer on navigation, and when the viewport grows past the breakpoint.
  useEffect(() => { setNavOpen(false) }, [pathname, isMobile])

  const closeNav = () => {
    setNavOpen(false)
    menuBtnRef.current?.focus()
  }

  return (
    <div className={styles.layout}>
      {isMobile && (
        <header className={styles.topbar}>
          <button
            ref={menuBtnRef}
            className={styles.menuBtn}
            onClick={() => setNavOpen(true)}
            aria-label={finishedDocs > 0 ? `Open navigation menu, ${finishedDocs} finished ${finishedDocs === 1 ? 'document' : 'documents'}` : 'Open navigation menu'}
            aria-expanded={navOpen}
            aria-controls="app-sidebar"
          >
            <Menu size={20} />
            {finishedDocs > 0 && <span className={styles.menuDot} aria-hidden="true" />}
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

      <Sidebar id="app-sidebar" drawer={isMobile} open={navOpen} onClose={closeNav} finishedDocs={finishedDocs} />

      <main className={styles.main}>
        <VerifyEmailBanner />
        <div className={styles.content}>
          <Outlet />
        </div>
      </main>
    </div>
  )
}
