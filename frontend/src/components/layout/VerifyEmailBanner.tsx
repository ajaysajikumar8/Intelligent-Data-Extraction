import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { MailWarning } from 'lucide-react'
import { ApiError, auth } from '../../lib/api'
import { getUser, saveSession } from '../../lib/auth'
import { Button } from '../ui/Button'
import styles from './VerifyEmailBanner.module.css'

/**
 * Shown to signed-in users whose email isn't confirmed yet. Trial credits unlock on
 * verification, so this is the first thing a new user needs to act on.
 */
export function VerifyEmailBanner() {
  const [user, setUser] = useState(getUser())
  const [sending, setSending] = useState(false)

  // The link is usually opened in another tab: resync when the user comes back to this one.
  useEffect(() => {
    if (!user || user.emailVerifiedAt) return
    const refresh = () => {
      auth.me().then((data) => { saveSession(data); setUser(data.user) }).catch(() => {})
    }
    refresh()
    window.addEventListener('focus', refresh)
    return () => window.removeEventListener('focus', refresh)
  }, [user])

  if (!user || user.emailVerifiedAt) return null

  const resend = async () => {
    setSending(true)
    try {
      await auth.resendVerification()
      toast.success(`Verification email sent to ${user.email}`)
    } catch (err: unknown) {
      toast.error(err instanceof ApiError ? err.message : 'Could not send the email. Try again shortly.')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className={styles.banner} role="status">
      <MailWarning size={18} className={styles.icon} aria-hidden="true" />
      <p className={styles.text}>
        <strong>Verify your email</strong> to unlock your free extractions. We sent a link to {user.email}.
      </p>
      <Button size="sm" variant="secondary" loading={sending} onClick={resend}>
        Resend email
      </Button>
    </div>
  )
}
