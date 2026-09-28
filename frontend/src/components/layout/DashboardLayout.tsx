import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import styles from './DashboardLayout.module.css'

/**
 * DashboardLayout — shell for all authenticated pages.
 * Fixed sidebar left + scrollable main content right.
 */
export function DashboardLayout() {
  return (
    <div className={styles.layout}>
      <Sidebar />
      <main className={styles.main}>
        <div className={styles.content}>
          <Outlet />
        </div>
      </main>
    </div>
  )
}
