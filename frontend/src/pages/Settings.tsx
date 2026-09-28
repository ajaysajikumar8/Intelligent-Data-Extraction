import { useEffect, useState } from 'react'
import { Copy, KeyRound, RefreshCw, Shield, Users, Webhook } from 'lucide-react'
import toast from 'react-hot-toast'
import { workspaces, webhooks } from '../lib/api'
import { getUser, getWorkspace, setWorkspace } from '../lib/auth'
import type { WorkspaceMember, WorkspaceResponse } from '../lib/types'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { Badge } from '../components/ui/Badge'
import { ThemeSelector } from '../components/ui/ThemeSelector'
import { Skeleton } from '../components/ui/Skeleton'
import styles from './Settings.module.css'

export function Settings() {
  const user = getUser()
  const [ws, setWs] = useState<WorkspaceResponse | null>(getWorkspace())
  const [members, setMembers] = useState<WorkspaceMember[]>([])
  const [wsName, setWsName] = useState(ws?.name ?? '')
  const [savingName, setSavingName] = useState(false)
  const [rotatingKey, setRotatingKey] = useState(false)
  const [apiKeyVisible, setApiKeyVisible] = useState(false)
  const [loadingMembers, setLoadingMembers] = useState(true)

  const [inboundUrl, setInboundUrl] = useState<string | null>(null)
  const [inboundVisible, setInboundVisible] = useState(false)
  const [rotatingInbound, setRotatingInbound] = useState(false)
  const [showInboundDocs, setShowInboundDocs] = useState(false)

  useEffect(() => {
    workspaces.listMembers().then(setMembers).finally(() => setLoadingMembers(false))
    webhooks.getInboundUrl().then(res => setInboundUrl(res.inboundUrl)).catch(() => {})
  }, [])

  const handleSaveName = async () => {
    if (!wsName.trim()) return
    setSavingName(true)
    try {
      const updated = await workspaces.update(wsName.trim())
      setWs(updated)
      setWorkspace(updated)
      toast.success('Workspace name updated')
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Update failed')
    } finally { setSavingName(false) }
  }

  const handleRotateKey = async () => {
    if (!confirm('Rotate the API key? The old key will stop working immediately.')) return
    setRotatingKey(true)
    try {
      const { apiKey } = await workspaces.rotateApiKey()
      if (ws) {
        const updated = { ...ws, apiKey }
        setWs(updated)
        setWorkspace(updated)
      }
      toast.success('API key rotated')
      setApiKeyVisible(true)
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Rotation failed')
    } finally { setRotatingKey(false) }
  }

  const copyKey = () => {
    navigator.clipboard.writeText(ws?.apiKey ?? '').then(() => toast.success('Copied!'))
  }

  const handleRotateInbound = async () => {
    if (!confirm('Rotate the Inbound Webhook URL? Integrations using the old URL will break immediately.')) return
    setRotatingInbound(true)
    try {
      const res = await webhooks.rotateInboundSecret()
      setInboundUrl(res.inboundUrl)
      toast.success('Inbound URL rotated')
      setInboundVisible(true)
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Rotation failed')
    } finally { setRotatingInbound(false) }
  }

  const copyInbound = () => {
    if (inboundUrl) {
      navigator.clipboard.writeText(inboundUrl).then(() => toast.success('Copied!'))
    }
  }

  const maskedKey = ws?.apiKey
    ? ws.apiKey.slice(0, 8) + '••••••••••••••••' + ws.apiKey.slice(-4)
    : ''

  const maskedInbound = inboundUrl
    ? inboundUrl.slice(0, 30) + '••••••••••••••••••••••••'
    : ''

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Settings</h1>
        <p className={styles.sub}>Manage your workspace, API access, and preferences.</p>
      </div>

      {/* Appearance */}
      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <Shield size={18} />
          <h2 className={styles.sectionTitle}>Appearance</h2>
        </div>
        <div className={styles.card}>
          <div className={styles.row}>
            <div>
              <p className={styles.rowLabel}>Theme</p>
              <p className={styles.rowDesc}>Choose your preferred colour scheme. System follows your OS setting.</p>
            </div>
            <ThemeSelector />
          </div>
        </div>
      </section>

      {/* Workspace */}
      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <Shield size={18} />
          <h2 className={styles.sectionTitle}>Workspace</h2>
        </div>
        <div className={styles.card}>
          <div className={styles.fieldGroup}>
            <Input
              label="Workspace name"
              id="settings-ws-name"
              value={wsName}
              onChange={(e) => setWsName(e.target.value)}
            />
            <Button loading={savingName} onClick={handleSaveName} size="sm" variant="secondary">
              Save
            </Button>
          </div>
          <div className={styles.metaRow}>
            <span className={styles.metaItem}><strong>Slug:</strong> {ws?.slug}</span>
            <span className={styles.metaItem}><strong>ID:</strong> {ws?.id?.slice(0, 12)}…</span>
          </div>
        </div>
      </section>

      {/* API Key */}
      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <KeyRound size={18} />
          <h2 className={styles.sectionTitle}>API Key</h2>
        </div>
        <div className={styles.card}>
          <p className={styles.rowDesc}>
            Use this key in the <code>X-API-Key</code> header to authenticate programmatic requests.
            Keep it secret — treat it like a password.
          </p>
          <div className={styles.keyRow}>
            <code className={styles.keyDisplay}>
              {apiKeyVisible ? ws?.apiKey : maskedKey}
            </code>
            <div className={styles.keyActions}>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setApiKeyVisible((v) => !v)}
              >
                {apiKeyVisible ? 'Hide' : 'Show'}
              </Button>
              <Button variant="ghost" size="sm" onClick={copyKey}>
                <Copy size={13} /> Copy
              </Button>
              <Button
                variant="secondary"
                size="sm"
                loading={rotatingKey}
                onClick={handleRotateKey}
              >
                <RefreshCw size={13} /> Rotate
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* Inbound Webhook */}
      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <Webhook size={18} />
          <h2 className={styles.sectionTitle}>Inbound Webhook</h2>
        </div>
        <div className={styles.card}>
          <p className={styles.rowDesc}>
            Use this unique URL to pipe data into the extraction engine from Zapier, Make.com, or custom scripts without needing authentication headers.
          </p>
          <div className={styles.keyRow}>
            <code className={styles.keyDisplay}>
              {inboundVisible ? inboundUrl : maskedInbound}
            </code>
            <div className={styles.keyActions}>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setInboundVisible((v) => !v)}
              >
                {inboundVisible ? 'Hide' : 'Show'}
              </Button>
              <Button variant="ghost" size="sm" onClick={copyInbound}>
                <Copy size={13} /> Copy
              </Button>
              <Button
                variant="secondary"
                size="sm"
                loading={rotatingInbound}
                onClick={handleRotateInbound}
              >
                <RefreshCw size={13} /> Rotate
              </Button>
            </div>
          </div>

          <div style={{ marginTop: '1rem' }}>
            <Button variant="ghost" size="sm" onClick={() => setShowInboundDocs(d => !d)}>
              {showInboundDocs ? 'Hide Integration Guide' : 'Show Integration Guide'}
            </Button>
            
            {showInboundDocs && (
              <div className={styles.docsBlock}>
                <h4>Universal Webhook</h4>
                <p>Send a POST request with form-data or JSON. Accepted fields:</p>
                <ul>
                  <li><code>rawInput</code>, <code>text</code>, or <code>body</code>: The raw text content to process.</li>
                  <li><code>file</code> or <code>attachment</code>: A PDF or image file (up to 20MB).</li>
                </ul>
                <h4>SendGrid Inbound Parse</h4>
                <p>
                  To use SendGrid Inbound Parse, append <code>/sendgrid</code> to the base path of your unique URL. It automatically parses SendGrid's multipart format.
                </p>
                <pre><code>curl -X POST {inboundUrl} \
  -F "rawInput=Extract this invoice details..." \
  -F "file=@invoice.pdf"</code></pre>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Members */}
      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <Users size={18} />
          <h2 className={styles.sectionTitle}>Members</h2>
        </div>
        <div className={styles.card} style={{ padding: 0, overflow: 'hidden' }}>
          <table className={styles.membersTable}>
            <thead>
              <tr>
                <th>Member</th>
                <th>Role</th>
                <th>Joined</th>
              </tr>
            </thead>
            <tbody>
              {loadingMembers
                ? Array.from({ length: 2 }).map((_, i) => (
                    <tr key={i}>
                      <td><Skeleton height={14} width="60%" /></td>
                      <td><Skeleton height={14} width="40%" /></td>
                      <td><Skeleton height={14} width="40%" /></td>
                    </tr>
                  ))
                : members.map((m) => (
                    <tr key={m.id} className={m.id === user?.id ? styles.currentUser : ''}>
                      <td>
                        <div className={styles.memberInfo}>
                          <div className={styles.memberAvatar}>
                            {(m.name ?? m.email)[0].toUpperCase()}
                          </div>
                          <div>
                            <div className={styles.memberName}>{m.name ?? '—'}</div>
                            <div className={styles.memberEmail}>{m.email}</div>
                          </div>
                        </div>
                      </td>
                      <td>
                        <Badge variant={m.role === 'OWNER' ? 'accent' : 'neutral'} dot={false}>
                          {m.role}
                        </Badge>
                      </td>
                      <td className={styles.dateCell}>{new Date(m.createdAt).toLocaleDateString()}</td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
