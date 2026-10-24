import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { CheckCircle2, MailWarning, Zap } from 'lucide-react'
import { auth } from '../lib/api'
import { getToken, saveSession } from '../lib/auth'
import { Button } from '../components/ui/Button'
import styles from './Login.module.css'

type State =
  | { kind: 'loading' }
  | { kind: 'done'; granted: number }
  | { kind: 'error'; message: string }

/** Landing page for the emailed verification link. Public: it may open in another browser. */
export function VerifyEmail() {
  const [params] = useSearchParams()
  const token = params.get('token')
  const [state, setState] = useState<State>(
    token ? { kind: 'loading' } : { kind: 'error', message: 'This verification link is incomplete.' },
  )
  // StrictMode runs effects twice in dev; the endpoint is idempotent but the grant message isn't.
  const started = useRef(false)

  useEffect(() => {
    if (!token || started.current) return
    started.current = true
    auth.verifyEmail(token)
      .then(async (res) => {
        setState({ kind: 'done', granted: res.trialExtractionsGranted })
        // If this browser is signed in, refresh the cached user/workspace (verified flag, credits).
        if (getToken()) {
          try { saveSession(await auth.me()) } catch { /* the next page load will resync */ }
        }
      })
      .catch((err: unknown) =>
        setState({ kind: 'error', message: err instanceof Error ? err.message : 'Verification failed.' }),
      )
  }, [token])

  const signedIn = getToken() !== null

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.logoWrap}>
          <div className={styles.logo}><Zap size={22} /></div>
        </div>

        {state.kind === 'loading' && <h1 className={styles.title}>Verifying your email…</h1>}

        {state.kind === 'done' && (
          <>
            <CheckCircle2 size={36} color="var(--color-success)" aria-hidden="true" />
            <h1 className={styles.title}>Email verified</h1>
            <p className={styles.sub}>
              {state.granted > 0
                ? `Your workspace is active with ${state.granted} free extractions.`
                : 'Your email address is confirmed.'}
            </p>
            <Link to={signedIn ? '/dashboard' : '/login'} style={{ width: '100%' }}>
              <Button size="lg" style={{ width: '100%' }}>
                {signedIn ? 'Go to dashboard' : 'Sign in'}
              </Button>
            </Link>
          </>
        )}

        {state.kind === 'error' && (
          <>
            <MailWarning size={36} color="var(--color-error)" aria-hidden="true" />
            <h1 className={styles.title}>Link not valid</h1>
            <p className={styles.sub}>{state.message}</p>
            <Link to={signedIn ? '/dashboard' : '/login'} style={{ width: '100%' }}>
              <Button variant="secondary" size="lg" style={{ width: '100%' }}>
                {signedIn ? 'Back to dashboard' : 'Sign in to request a new link'}
              </Button>
            </Link>
          </>
        )}
      </div>
    </div>
  )
}
