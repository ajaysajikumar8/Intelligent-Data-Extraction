import { useEffect, useRef } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import {
  BarChart3,
  FileText,
  Layers,
  LogOut,
  Settings,
  Upload,
  Zap,
  Webhook
} from 'lucide-react'
import { clearSession, getUser } from '../../lib/auth'
import { APP_NAME } from '../../lib/brand'
import styles from './Sidebar.module.css'

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Overview',   Icon: BarChart3 },
  { to: '/submit',    label: 'Submit',      Icon: Upload },
  { to: '/logs',      label: 'Logs',        Icon: FileText },
  { to: '/templates', label: 'Templates',   Icon: Layers },
  { to: '/integrations', label: 'Integrations', Icon: Webhook },
  { to: '/settings',  label: 'Settings',    Icon: Settings },
]

const FOCUSABLE = 'a[href], button:not([disabled])'

interface SidebarProps {
  id: string
  /** Render as an off-canvas drawer (mobile) instead of a fixed rail. */
  drawer: boolean
  open: boolean
  onClose: () => void
}

export function Sidebar({ id, drawer, open, onClose }: SidebarProps) {
  const navigate = useNavigate()
  const user = getUser()
  const ref = useRef<HTMLElement>(null)

  // A closed drawer is off-screen: keep it out of the tab order and a11y tree.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (drawer && !open) el.setAttribute('inert', '')
    else el.removeAttribute('inert')
  }, [drawer, open])

  // Drawer open: move focus in, trap Tab, close on Esc.
  useEffect(() => {
    const el = ref.current
    if (!drawer || !open || !el) return
    el.querySelector<HTMLElement>(FOCUSABLE)?.focus()

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { onClose(); return }
      if (e.key !== 'Tab') return
      const items = el.querySelectorAll<HTMLElement>(FOCUSABLE)
      if (items.length === 0) return
      const first = items[0]
      const last = items[items.length - 1]
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [drawer, open, onClose])

  const handleLogout = () => {
    clearSession()
    navigate('/login', { replace: true })
  }

  const initials = user?.name
    ? user.name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2)
    : user?.email?.[0]?.toUpperCase() ?? '?'

  return (
    <aside
      id={id}
      ref={ref}
      className={[styles.sidebar, drawer ? styles.drawer : '', drawer && open ? styles.drawerOpen : ''].filter(Boolean).join(' ')}
      aria-label={drawer ? 'Navigation menu' : undefined}
    >
      {/* Brand */}
      <div className={styles.brand}>
        <div className={styles.logo}>
          <Zap size={18} />
        </div>
        <span className={styles.brandName}>{APP_NAME}</span>
      </div>

      {/* Navigation */}
      <nav className={styles.nav} aria-label="Main navigation">
        {NAV_ITEMS.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              [styles.navItem, isActive ? styles.active : '']
                .filter(Boolean)
                .join(' ')
            }
          >
            <Icon size={17} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Footer: user + logout */}
      <div className={styles.footer}>
        <div className={styles.userInfo}>
          <div className={styles.avatar}>{initials}</div>
          <div className={styles.userMeta}>
            <span className={styles.userName}>{user?.name ?? 'User'}</span>
            <span className={styles.userEmail}>{user?.email}</span>
          </div>
        </div>
        <button
          className={styles.logoutBtn}
          onClick={handleLogout}
          title="Sign out"
          aria-label="Sign out"
        >
          <LogOut size={16} />
        </button>
      </div>
    </aside>
  )
}
