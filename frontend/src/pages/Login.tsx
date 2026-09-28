import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Mail, Lock, Zap } from 'lucide-react'
import toast from 'react-hot-toast'
import { auth } from '../lib/api'
import { saveSession } from '../lib/auth'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import styles from './Login.module.css'

export function Login() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const isEmailValid = email.includes('@')
  const isPasswordValid = password.length > 0
  const isFormValid = isEmailValid && isPasswordValid
  
  let missingReq = ''
  if (!isEmailValid) missingReq = 'Valid email is required'
  else if (!isPasswordValid) missingReq = 'Password is required'

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await auth.login(email, password)
      saveSession(data)
      navigate('/dashboard', { replace: true })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Login failed'
      setError(msg)
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        {/* Logo */}
        <div className={styles.logoWrap}>
          <div className={styles.logo}><Zap size={22} /></div>
        </div>

        <h1 className={styles.title}>Welcome back</h1>
        <p className={styles.sub}>Sign in to your workspace</p>

        <form className={styles.form} onSubmit={handleSubmit} noValidate>
          <Input
            label="Email"
            type="email"
            id="login-email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            leftIcon={<Mail size={15} />}
            required
            autoComplete="email"
            autoFocus
          />
          <Input
            label="Password"
            type="password"
            id="login-password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            leftIcon={<Lock size={15} />}
            required
            autoComplete="current-password"
            error={error}
          />
          
          {!isFormValid && !error && (
            <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)', marginBottom: '0.5rem', textAlign: 'center' }}>
              {missingReq}
            </div>
          )}

          <Button type="submit" disabled={!isFormValid} loading={loading} size="lg" style={{ width: '100%' }}>
            Sign in
          </Button>
        </form>

        <p className={styles.footer}>
          Don't have an account?{' '}
          <Link to="/signup">Create one</Link>
        </p>
      </div>
    </div>
  )
}
