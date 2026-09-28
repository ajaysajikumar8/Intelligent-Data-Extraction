import { Monitor, Moon, Sun } from 'lucide-react'
import { useTheme } from '../../hooks/useTheme'
import type { ThemeMode } from '../../lib/types'
import styles from './ThemeSelector.module.css'

const OPTIONS: { mode: ThemeMode; label: string; Icon: typeof Sun }[] = [
  { mode: 'system', label: 'System', Icon: Monitor },
  { mode: 'light',  label: 'Light',  Icon: Sun },
  { mode: 'dark',   label: 'Dark',   Icon: Moon },
]

export function ThemeSelector() {
  const { themeMode, setThemeMode } = useTheme()

  return (
    <div className={styles.selector} role="group" aria-label="Theme preference">
      {OPTIONS.map(({ mode, label, Icon }) => (
        <button
          key={mode}
          className={[
            styles.option,
            themeMode === mode ? styles.active : '',
          ]
            .filter(Boolean)
            .join(' ')}
          onClick={() => setThemeMode(mode)}
          aria-pressed={themeMode === mode}
          title={`Switch to ${label} theme`}
        >
          <Icon size={14} />
          <span>{label}</span>
        </button>
      ))}
    </div>
  )
}
