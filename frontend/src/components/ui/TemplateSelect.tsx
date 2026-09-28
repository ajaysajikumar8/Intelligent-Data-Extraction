import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown, FileCode, Sparkles } from 'lucide-react'
import type { TemplateResponse } from '../../lib/types'
import styles from './TemplateSelect.module.css'

interface TemplateSelectProps {
  templates: TemplateResponse[]
  value: string
  onChange: (templateId: string) => void
  disabled?: boolean
}

export function TemplateSelect({ templates, value, onChange, disabled = false }: TemplateSelectProps) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const activeTemplates = templates.filter((t) => t.isActive)
  const selectedTemplate = activeTemplates.find((t) => t.id === value)

  // Click outside listener to dismiss popover
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleSelect = (id: string) => {
    onChange(id)
    setOpen(false)
  }

  return (
    <div className={styles.container} ref={containerRef}>
      {/* Trigger Button */}
      <button
        type="button"
        className={[styles.trigger, open ? styles.triggerOpen : ''].filter(Boolean).join(' ')}
        onClick={() => !disabled && setOpen((prev) => !prev)}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <div className={styles.triggerLeft}>
          <div
            className={[
              styles.iconWrapper,
              value === '' ? styles.iconWrapperAuto : '',
            ].filter(Boolean).join(' ')}
          >
            {value === '' ? <Sparkles size={16} /> : <FileCode size={16} />}
          </div>
          <div className={styles.triggerTextGroup}>
            <span className={styles.triggerTitle}>
              {value === '' ? '✨ Auto-Detect via AI' : selectedTemplate?.name ?? 'Select Template'}
            </span>
            <span className={styles.triggerSub}>
              {value === ''
                ? 'Intent Classifier matches content automatically'
                : `v${selectedTemplate?.version ?? 1} · ${selectedTemplate?.fieldCount ?? 0} fields`}
            </span>
          </div>
        </div>

        <div className={styles.triggerRight}>
          <ChevronDown
            size={16}
            className={[styles.chevron, open ? styles.chevronOpen : ''].filter(Boolean).join(' ')}
          />
        </div>
      </button>

      {/* Menu Popover */}
      {open && (
        <div className={styles.menu} role="listbox">
          {/* Option 1: Auto-Detect */}
          <button
            type="button"
            className={[styles.option, value === '' ? styles.optionSelected : ''].filter(Boolean).join(' ')}
            onClick={() => handleSelect('')}
            role="option"
            aria-selected={value === ''}
          >
            <div className={styles.optionLeft}>
              <div className={[styles.iconWrapper, styles.iconWrapperAuto].join(' ')}>
                <Sparkles size={16} />
              </div>
              <div className={styles.optionContent}>
                <div className={styles.optionHeader}>
                  <span className={styles.optionTitle}>✨ Auto-Detect via AI</span>
                  <span className={styles.badgeRecommended}>AI Classifier</span>
                </div>
                <span className={styles.optionDesc}>
                  Gemini reads document text/file and selects the matching active template automatically.
                </span>
              </div>
            </div>
            {value === '' && <Check size={16} className={styles.checkIcon} />}
          </button>

          {/* Option N: Explicit active templates */}
          {activeTemplates.map((tmpl) => {
            const isSelected = value === tmpl.id
            const fieldKeys = typeof tmpl.schema === 'object' && tmpl.schema
              ? Object.keys(tmpl.schema).join(', ')
              : ''

            return (
              <button
                key={tmpl.id}
                type="button"
                className={[styles.option, isSelected ? styles.optionSelected : ''].filter(Boolean).join(' ')}
                onClick={() => handleSelect(tmpl.id)}
                role="option"
                aria-selected={isSelected}
              >
                <div className={styles.optionLeft}>
                  <div className={styles.iconWrapper}>
                    <FileCode size={16} />
                  </div>
                  <div className={styles.optionContent}>
                    <div className={styles.optionHeader}>
                      <span className={styles.optionTitle}>{tmpl.name}</span>
                      <span className={styles.badgeMeta}>v{tmpl.version}</span>
                      <span className={styles.badgeMeta}>{tmpl.fieldCount} fields</span>
                    </div>
                    <span className={styles.optionDesc}>
                      {fieldKeys ? `Fields: ${fieldKeys}` : tmpl.description || 'Target schema extraction template.'}
                    </span>
                  </div>
                </div>
                {isSelected && <Check size={16} className={styles.checkIcon} />}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
