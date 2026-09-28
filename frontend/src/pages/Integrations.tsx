import { useEffect, useState } from 'react'
import { Plus, Webhook, Activity, CheckCircle2, XCircle, Trash2, Send } from 'lucide-react'
import toast from 'react-hot-toast'
import { webhooks } from '../lib/api'
import type { WebhookResponse, WebhookDeliveryResponse, WebhookEventType } from '../lib/types'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { Drawer } from '../components/ui/Drawer'
import { StackedDrawer, useStackedDrawer } from '../components/ui/StackedDrawer'
import styles from './Integrations.module.css'

const getPreviewPayload = (event: WebhookEventType | string) => {
  const base = {
    event: `extraction.${event.toLowerCase()}`,
    data: {
      documentId: "doc_123abc",
      workspaceId: "ws_456def",
      status: event,
    }
  }
  
  if (event === 'NEEDS_REVIEW') {
    return {
      ...base,
      data: {
        ...base.data,
        message: "Manual review required in dashboard"
      }
    }
  }
  
  return {
    ...base,
    data: {
      ...base.data,
      source: "API",
      templateId: "tmpl_789ghi",
      fileName: "invoice.pdf",
      mimeType: "application/pdf",
      extractedJson: event === 'SUCCESS' ? { invoice_no: "INV-100", amount: 500 } : null,
      confidenceScores: event === 'SUCCESS' ? { invoice_no: "High", amount: "High" } : null,
      validationErrors: event === 'FAILED' ? [{ field: "amount", message: "Required" }] : null,
      processingMs: 1450,
      createdAt: new Date().toISOString()
    }
  }
}

function CreateWebhookForm({ newUrl, setNewUrl, newDesc, setNewDesc, newEventTypes, setNewEventTypes, handleCreate, isSubmitting, setCreating }: any) {
  const { push } = useStackedDrawer()

  return (
    <div className={styles.form}>
      <Input 
        label="Webhook URL" 
        placeholder="https://hooks.zapier.com/..." 
        value={newUrl} 
        onChange={(e: any) => setNewUrl(e.target.value)} 
      />
      <Input 
        label="Description (Optional)" 
        placeholder="e.g. Invoices to Google Sheets" 
        value={newDesc} 
        onChange={(e: any) => setNewDesc(e.target.value)} 
      />
      
      <div className={styles.checkboxGroup}>
        <label className={styles.inputLabel}>Event Subscriptions</label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '8px' }}>
          {(['SUCCESS', 'NEEDS_REVIEW', 'FAILED', 'UNMATCHED'] as WebhookEventType[]).map(type => (
            <div key={type} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', flex: 1 }}>
                <input 
                  type="checkbox" 
                  checked={newEventTypes.includes(type)}
                  onChange={(e) => {
                    if (e.target.checked) setNewEventTypes((prev: any) => [...prev, type])
                    else setNewEventTypes((prev: any) => prev.filter((t: any) => t !== type))
                  }}
                />
                <span>{type}</span>
              </label>
              <Button 
                variant="ghost" 
                size="sm" 
                onClick={() => push({
                  id: `preview-${type}`,
                  title: `${type} Payload`,
                  content: (
                    <div style={{ paddingBottom: '24px' }}>
                      <p className={styles.desc} style={{ marginBottom: '16px' }}>This is the exact JSON structure your server will receive when this event occurs.</p>
                      <pre className={styles.mono} style={{ background: 'var(--bg-subtle)', padding: '16px', borderRadius: '8px', overflowX: 'auto', border: '1px solid var(--border-color)' }}>
                        {JSON.stringify(getPreviewPayload(type), null, 2)}
                      </pre>
                    </div>
                  )
                })}
              >
                Preview
              </Button>
            </div>
          ))}
        </div>
      </div>

      <div className={styles.formActions}>
        <Button variant="ghost" onClick={() => setCreating(false)}>Cancel</Button>
        <Button onClick={handleCreate} loading={isSubmitting}>Save Webhook</Button>
      </div>
    </div>
  )
}


export function Integrations() {
  const [items, setItems] = useState<WebhookResponse[]>([])
  const [loading, setLoading] = useState(true)

  // Drawer states
  const [activeWebhook, setActiveWebhook] = useState<WebhookResponse | null>(null)
  const [deliveries, setDeliveries] = useState<WebhookDeliveryResponse[]>([])
  const [loadingDeliveries, setLoadingDeliveries] = useState(false)

  // Create states
  const [creating, setCreating] = useState(false)
  const [newUrl, setNewUrl] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [newEventTypes, setNewEventTypes] = useState<WebhookEventType[]>(['SUCCESS', 'NEEDS_REVIEW'])
  const [isSubmitting, setIsSubmitting] = useState(false)

  const fetchWebhooks = () => {
    setLoading(true)
    webhooks.list()
      .then(setItems)
      .catch((e: Error) => toast.error('Failed to load webhooks: ' + e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchWebhooks()
  }, [])

  const handleCreate = async () => {
    if (!newUrl.trim()) return toast.error('URL is required')
    if (newEventTypes.length === 0) return toast.error('Select at least one event type')
    try {
      setIsSubmitting(true)
      await webhooks.create({ url: newUrl.trim(), description: newDesc.trim() || undefined, eventTypes: newEventTypes })
      toast.success('Webhook created')
      setCreating(false)
      setNewUrl('')
      setNewDesc('')
      setNewEventTypes(['SUCCESS', 'NEEDS_REVIEW'])
      fetchWebhooks()
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Creation failed')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('Are you sure you want to delete this webhook?')) return
    try {
      await webhooks.delete(id)
      toast.success('Webhook deleted')
      if (activeWebhook?.id === id) setActiveWebhook(null)
      fetchWebhooks()
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Deletion failed')
    }
  }

  const handlePing = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await webhooks.ping(id)
      toast.success('Ping payload dispatched. Check deliveries for result.')
      if (activeWebhook?.id === id) {
        loadDeliveries(id)
      }
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Ping failed')
    }
  }

  const openDrawer = (wh: WebhookResponse) => {
    setActiveWebhook(wh)
    loadDeliveries(wh.id)
  }

  const loadDeliveries = (id: string) => {
    setLoadingDeliveries(true)
    webhooks.deliveries(id)
      .then(setDeliveries)
      .catch(() => toast.error('Failed to load deliveries'))
      .finally(() => setLoadingDeliveries(false))
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Outbound Integrations</h1>
          <p className={styles.sub}>Automatically push extracted data to your servers or workflow apps.</p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus size={16} /> Add Webhook
        </Button>
      </div>

      {loading ? (
        <div className={styles.empty}>Loading integrations...</div>
      ) : items.length === 0 ? (
        <div className={styles.empty}>
          <Webhook size={48} style={{ opacity: 0.2, marginBottom: '1rem' }} />
          <h3>No webhooks configured</h3>
          <p style={{ marginTop: '0.5rem' }}>Push JSON to Zapier, Make, or your custom API.</p>
        </div>
      ) : (
        <div className={styles.list}>
          {items.map(wh => (
            <div key={wh.id} className={styles.card} onClick={() => openDrawer(wh)}>
              <div className={styles.cardHeader}>
                <div>
                  <div className={styles.url}>{wh.url}</div>
                  {wh.description && <div className={styles.desc}>{wh.description}</div>}
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <Button variant="secondary" size="sm" onClick={(e) => handlePing(wh.id, e)}>
                    <Send size={14} /> Ping
                  </Button>
                  <Button variant="ghost" size="sm" onClick={(e) => handleDelete(wh.id, e)}>
                    <Trash2 size={14} className={styles.iconError} />
                  </Button>
                </div>
              </div>
              <div className={styles.meta}>
                <span className={wh.isActive ? styles.statusActive : styles.statusInactive}>
                  {wh.isActive ? 'Active' : 'Disabled'}
                </span>
                <span>Events: {wh.eventTypes?.length ? wh.eventTypes.join(', ') : 'All'}</span>
                {wh.failureCount > 0 && <span className={styles.iconError}>Failures: {wh.failureCount}</span>}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Modal Drawer Using StackedDrawer */}
      <StackedDrawer 
        isOpen={creating} 
        onClose={() => setCreating(false)} 
        rootScreen={{
          id: 'root',
          title: 'New Webhook',
          content: (
            <CreateWebhookForm 
              newUrl={newUrl}
              setNewUrl={setNewUrl}
              newDesc={newDesc}
              setNewDesc={setNewDesc}
              newEventTypes={newEventTypes}
              setNewEventTypes={setNewEventTypes}
              handleCreate={handleCreate}
              isSubmitting={isSubmitting}
              setCreating={setCreating}
            />
          )
        }}
      />

      {/* Webhook Deliveries Drawer */}
      <Drawer isOpen={!!activeWebhook} onClose={() => setActiveWebhook(null)} title="Webhook Details">
        {activeWebhook && (
          <div className={styles.drawerContent}>
            <div>
              <div className={styles.sectionTitle}><Webhook size={16} /> Configuration</div>
              <p className={styles.mono} style={{ wordBreak: 'break-all' }}>{activeWebhook.url}</p>
              <p className={styles.monoMuted}>Secret: {activeWebhook.secret}</p>
            </div>

            <div>
              <div className={styles.sectionTitle}>
                <Activity size={16} /> Recent Deliveries
                <Button variant="ghost" size="sm" style={{ marginLeft: 'auto' }} onClick={() => loadDeliveries(activeWebhook.id)}>
                  Refresh
                </Button>
              </div>
              
              {loadingDeliveries ? (
                <p className={styles.desc}>Loading deliveries...</p>
              ) : deliveries.length === 0 ? (
                <p className={styles.desc}>No delivery attempts yet.</p>
              ) : (
                <div className={styles.deliveriesList}>
                  {deliveries.map(d => (
                    <div key={d.id} className={styles.deliveryItem}>
                      <div className={styles.deliveryHeader}>
                        {d.statusCode && d.statusCode >= 200 && d.statusCode < 300 ? (
                          <CheckCircle2 size={16} className={styles.iconSuccess} />
                        ) : (
                          <XCircle size={16} className={styles.iconError} />
                        )}
                        <span className={styles.mono}>HTTP {d.statusCode || 'ERR'}</span>
                        <span className={styles.monoMuted}>{d.durationMs}ms</span>
                        <span className={styles.dateMuted}>{new Date(d.createdAt).toLocaleString()}</span>
                      </div>
                      {d.responseBody && (
                        <div className={styles.deliveryBody}>
                          {d.responseBody}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </Drawer>
    </div>
  )
}
