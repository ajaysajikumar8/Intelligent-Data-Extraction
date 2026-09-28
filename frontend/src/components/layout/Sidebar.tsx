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
import styles from './Sidebar.module.css'

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Overview',   Icon: BarChart3 },
  { to: '/submit',    label: 'Submit',      Icon: Upload },
  { to: '/logs',      label: 'Logs',        Icon: FileText },
  { to: '/templates', label: 'Templates',   Icon: Layers },
  { to: '/integrations', label: 'Integrations', Icon: Webhook },
  { to: '/settings',  label: 'Settings',    Icon: Settings },
]

export function Sidebar() {
  const navigate = useNavigate()
  const user = getUser()

  const handleLogout = () => {
    clearSession()
    navigate('/login', { replace: true })
  }

  const initials = user?.name
    ? user.name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2)
    : user?.email?.[0]?.toUpperCase() ?? '?'

  return (
    <aside className={styles.sidebar}>
      {/* Brand */}
      <div className={styles.brand}>
        <div className={styles.logo}>
          <Zap size={18} />
        </div>
        <div>
          <span className={styles.brandName}>IDE</span>
          <span className={styles.brandSub}>Dashboard</span>
        </div>
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
