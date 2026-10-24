import { Link } from 'react-router-dom'
import { Check, ChevronRight } from 'lucide-react'
import styles from './FirstRunChecklist.module.css'

interface Props {
  hasTemplate: boolean
  hasExtraction: boolean
  hasOwnKey: boolean
  trialRemaining: number
}

interface Step {
  id: string
  title: string
  detail: string
  to: string
  done: boolean
  locked?: boolean
}

/**
 * Getting-started checklist for new workspaces. Progress is derived from real data (templates,
 * extractions, key) rather than stored, so it can never drift, and the card disappears once
 * everything is done.
 */
export function FirstRunChecklist({ hasTemplate, hasExtraction, hasOwnKey, trialRemaining }: Props) {
  const needsKeyNow = !hasOwnKey && trialRemaining <= 0

  const keyStep: Step = {
    id: 'key',
    title: 'Add your Gemini API key',
    detail: hasOwnKey
      ? 'Your own key is used for every extraction.'
      : needsKeyNow
        ? 'Required before you can extract — your free trial is used up.'
        : `${trialRemaining} free ${trialRemaining === 1 ? 'extraction' : 'extractions'} left. Add your own key to keep going afterwards.`,
    to: '/settings',
    done: hasOwnKey,
  }
  const templateStep: Step = {
    id: 'template',
    title: 'Add a template',
    detail: 'Pick one from the library (e.g. Standard Invoice) or define your own fields.',
    to: '/templates',
    done: hasTemplate,
  }
  const sampleStep: Step = {
    id: 'sample',
    title: 'Run a sample extraction',
    detail: 'We pre-fill an example invoice — just press Submit.',
    to: '/submit?sample=1',
    done: hasExtraction,
    locked: !hasTemplate || needsKeyNow,
  }

  // With no trial left the key blocks everything, so it goes first; otherwise it comes last.
  const steps = needsKeyNow ? [keyStep, templateStep, sampleStep] : [templateStep, sampleStep, keyStep]
  const completed = steps.filter((s) => s.done).length
  if (completed === steps.length) return null

  return (
    <section className={styles.card} aria-labelledby="first-run-title">
      <div className={styles.head}>
        <h2 id="first-run-title" className={styles.title}>Get started</h2>
        <span className={styles.count}>{completed} of {steps.length} done</span>
      </div>
      <ol className={styles.list}>
        {steps.map((s) => {
          const body = (
            <>
              <span className={`${styles.mark} ${s.done ? styles.markDone : ''}`} aria-hidden="true">
                {s.done && <Check size={13} />}
              </span>
              <span className={styles.text}>
                <span className={`${styles.stepTitle} ${s.done ? styles.stepTitleDone : ''}`}>{s.title}</span>
                <span className={styles.detail}>{s.detail}</span>
              </span>
              {!s.done && !s.locked && <ChevronRight size={16} className={styles.chevron} />}
            </>
          )
          return (
            <li key={s.id}>
              {s.done || s.locked ? (
                <div className={`${styles.step} ${s.locked ? styles.locked : ''}`}>{body}</div>
              ) : (
                <Link to={s.to} className={`${styles.step} ${styles.stepLink}`}>{body}</Link>
              )}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
