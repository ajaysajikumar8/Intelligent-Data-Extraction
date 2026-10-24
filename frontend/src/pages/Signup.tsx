import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Mail, Lock, User, Building2, Zap } from 'lucide-react'
import toast from 'react-hot-toast'
import { ApiError, auth } from '../lib/api'
import { saveSession } from '../lib/auth'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import styles from './Login.module.css'

export function Signup() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    email: '', password: '', name: '', workspaceName: '',
  })
  const [loading, setLoading] = useState(false)
  // Field-level messages (shown under the relevant input) vs. a form-level one (e.g. rate limit).
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState('')

  const isEmailValid = form.email.includes('@')
  const isPasswordValid = form.password.length >= 8
  const isFormValid = isEmailValid && isPasswordValid && form.name.trim().length > 0 && form.workspaceName.trim().length > 0
  
  let missingReq = ''
  if (!form.name.trim()) missingReq = 'Full name is required'
  else if (!form.workspaceName.trim()) missingReq = 'Workspace name is required'
  else if (!isEmailValid) missingReq = 'Valid email is required'
  else if (!isPasswordValid) missingReq = 'Password must be at least 8 characters'

  const update = (field: keyof typeof form) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setForm((prev) => ({ ...prev, [field]: e.target.value }))
      setFieldErrors((prev) => (prev[field] ? { ...prev, [field]: '' } : prev))
    }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setFormError('')
    setFieldErrors({})
    if (form.password.length < 8) {
      setFieldErrors({ password: 'Password must be at least 8 characters.' })
      return
    }
    setLoading(true)
    try {
      const data = await auth.signup({
        email: form.email,
        password: form.password,
        name: form.name || undefined,
        workspaceName: form.workspaceName || undefined,
      })
      saveSession(data)
      toast.success('Workspace created!')
      navigate('/dashboard', { replace: true })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Signup failed'
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length > 0) {
        setFieldErrors(err.fieldErrors)
      } else if (err instanceof ApiError && err.status === 400) {
        // Duplicate or disposable address: the problem is the email, so say so there.
        setFieldErrors({ email: msg })
      } else {
        setFormError(msg)
        toast.error(msg)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.logoWrap}>
          <div className={styles.logo}><Zap size={22} /></div>
        </div>

        <h1 className={styles.title}>Create your account</h1>
        <p className={styles.sub}>Set up your workspace in seconds</p>

        <form className={styles.form} onSubmit={handleSubmit} noValidate>
          <Input
            label="Full name"
            type="text"
            id="signup-name"
            placeholder="Jane Smith"
            value={form.name}
            onChange={update('name')}
            leftIcon={<User size={15} />}
            error={fieldErrors.name}
            autoFocus
          />
          <Input
            label="Workspace name"
            type="text"
            id="signup-workspace"
            placeholder="Acme Corp"
            value={form.workspaceName}
            onChange={update('workspaceName')}
            leftIcon={<Building2 size={15} />}
            error={fieldErrors.workspaceName}
          />
          <Input
            label="Email"
            type="email"
            id="signup-email"
            placeholder="you@example.com"
            value={form.email}
            onChange={update('email')}
            leftIcon={<Mail size={15} />}
            required
            error={fieldErrors.email}
          />
          <Input
            label="Password"
            type="password"
            id="signup-password"
            placeholder="Min. 8 characters"
            value={form.password}
            onChange={update('password')}
            leftIcon={<Lock size={15} />}
            required
            error={fieldErrors.password}
          />
          
          {formError && (
            <div role="alert" style={{ fontSize: '0.8rem', color: 'var(--color-error)', textAlign: 'center' }}>
              {formError}
            </div>
          )}

          {!isFormValid && !formError && (
            <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)', marginBottom: '0.5rem', textAlign: 'center' }}>
              {missingReq}
            </div>
          )}

          <Button type="submit" disabled={!isFormValid} loading={loading} size="lg" style={{ width: '100%' }}>
            Create workspace
          </Button>
        </form>

        <p className={styles.footer}>
          Already have an account?{' '}
          <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  )
}
