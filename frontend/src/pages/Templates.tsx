import { useEffect, useState } from 'react'
import { Layers, Pencil, Plus, Trash2, Copy, BookOpen } from 'lucide-react'
import toast from 'react-hot-toast'
import { templates as tmplApi } from '../lib/api'
import type { LibraryTemplateResponse, TemplateCreate, TemplateResponse, TemplateUpdate } from '../lib/types'
import { Button } from '../components/ui/Button'
import { Input, Textarea } from '../components/ui/Input'
import { Badge } from '../components/ui/Badge'
import { Modal } from '../components/ui/Modal'
import { Skeleton } from '../components/ui/Skeleton'
import styles from './Templates.module.css'

function parseSchema(raw: string): Record<string, unknown> | null {
  try { return JSON.parse(raw) } catch { return null }
}

export function Templates() {
  const [activeTab, setActiveTab] = useState<'my' | 'library'>('my')
  const [list, setList] = useState<TemplateResponse[]>([])
  const [libraryList, setLibraryList] = useState<LibraryTemplateResponse[]>([])
  const [loading, setLoading] = useState(true)
  
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<TemplateResponse | null>(null)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({ name: '', description: '', schema: '{\n  \n}' })
  const [schemaError, setSchemaError] = useState('')

  const load = () => {
    setLoading(true)
    Promise.all([tmplApi.list(), tmplApi.getLibrary()])
      .then(([myTemplates, libTemplates]) => {
        setList(myTemplates)
        setLibraryList(libTemplates)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const openCreate = () => {
    setEditing(null)
    setForm({ name: '', description: '', schema: '{\n  \n}' })
    setSchemaError('')
    setModalOpen(true)
  }

  const openEdit = (t: TemplateResponse) => {
    setEditing(t)
    setForm({ name: t.name, description: t.description ?? '', schema: JSON.stringify(t.schema, null, 2) })
    setSchemaError('')
    setModalOpen(true)
  }

  const handleSave = async () => {
    const parsed = parseSchema(form.schema)
    if (!parsed) { setSchemaError('Invalid JSON schema.'); return }
    if (!form.name.trim()) { toast.error('Name is required.'); return }
    setSaving(true)
    try {
      if (editing) {
        const payload: TemplateUpdate = { name: form.name, description: form.description || undefined, schema: parsed }
        await tmplApi.update(editing.id, payload)
        toast.success('Template updated')
      } else {
        const payload: TemplateCreate = { name: form.name, description: form.description || undefined, schema: parsed }
        await tmplApi.create(payload)
        toast.success('Template created')
      }
      setModalOpen(false)
      load()
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Save failed')
    } finally { setSaving(false) }
  }

  const handleToggle = async (t: TemplateResponse) => {
    try {
      await tmplApi.update(t.id, { isActive: !t.isActive })
      toast.success(t.isActive ? 'Template deactivated' : 'Template activated')
      load()
    } catch { toast.error('Update failed') }
  }

  const handleDelete = async (t: TemplateResponse) => {
    if (!confirm(`Delete "${t.name}"? This cannot be undone.`)) return
    try {
      await tmplApi.delete(t.id)
      toast.success('Template deleted')
      load()
    } catch { toast.error('Delete failed') }
  }

  const handleDuplicateLibrary = async (slug: string) => {
    try {
      await tmplApi.duplicateFromLibrary(slug)
      toast.success('Template added to your workspace')
      setActiveTab('my')
      load()
    } catch {
      toast.error('Failed to duplicate template')
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Templates</h1>
          <p className={styles.sub}>Define JSON schemas that Gemini uses as extraction targets.</p>
        </div>
        {activeTab === 'my' && (
          <Button onClick={openCreate}><Plus size={15} /> New template</Button>
        )}
      </div>

      <div className={styles.tabs}>
        <button 
          className={`${styles.tab} ${activeTab === 'my' ? styles.active : ''}`}
          onClick={() => setActiveTab('my')}
        >
          My Templates
        </button>
        <button 
          className={`${styles.tab} ${activeTab === 'library' ? styles.active : ''}`}
          onClick={() => setActiveTab('library')}
        >
          Template Library
        </button>
      </div>

      {loading ? (
        <div className={styles.grid}>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className={styles.card}>
              <Skeleton height={14} width="50%" />
              <Skeleton height={12} width="80%" />
              <Skeleton height={12} width="30%" />
            </div>
          ))}
        </div>
      ) : activeTab === 'my' ? (
        list.length === 0 ? (
          <div className={styles.empty}>
            <Layers size={40} style={{ color: 'var(--color-text-subtle)' }} />
            <p>No templates yet. Create your first one or add one from the library.</p>
            <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
              <Button onClick={openCreate}><Plus size={14} /> Create template</Button>
              <Button variant="secondary" onClick={() => setActiveTab('library')}><BookOpen size={14} /> Browse library</Button>
            </div>
          </div>
        ) : (
          <div className={styles.grid}>
            {list.map((t) => (
              <div key={t.id} className={[styles.card, !t.isActive ? styles.inactive : ''].filter(Boolean).join(' ')}>
                <div className={styles.cardTop}>
                  <div className={styles.cardTitleRow}>
                    <span className={styles.cardName}>{t.name}</span>
                    <Badge variant={t.isActive ? 'success' : 'neutral'} dot={false}>
                      {t.isActive ? 'Active' : 'Inactive'}
                    </Badge>
                  </div>
                  {t.description && <p className={styles.cardDesc}>{t.description}</p>}
                </div>
                <div className={styles.cardMeta}>
                  <span>{t.fieldCount} fields</span>
                  <span>v{t.version}</span>
                  <span>{new Date(t.updatedAt).toLocaleDateString()}</span>
                </div>
                <div className={styles.cardActions}>
                  <Button variant="ghost" size="sm" onClick={() => openEdit(t)}>
                    <Pencil size={13} /> Edit
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => handleToggle(t)}>
                    {t.isActive ? 'Deactivate' : 'Activate'}
                  </Button>
                  <Button variant="danger" size="sm" onClick={() => handleDelete(t)}>
                    <Trash2 size={13} />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )
      ) : (
        <div className={styles.grid}>
          {libraryList.map((t) => (
            <div key={t.slug} className={styles.card}>
              <div className={styles.cardTop}>
                <div className={styles.cardTitleRow}>
                  <span className={styles.cardName}>{t.name}</span>
                  <Badge variant="info" dot={false}>Pre-built</Badge>
                </div>
                {t.description && <p className={styles.cardDesc}>{t.description}</p>}
              </div>
              <div className={styles.cardMeta}>
                <span>{t.fieldCount} fields</span>
              </div>
              <div className={styles.cardActions}>
                <Button variant="secondary" size="sm" onClick={() => handleDuplicateLibrary(t.slug)}>
                  <Copy size={13} /> Add to my templates
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editing ? 'Edit template' : 'New template'}
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button loading={saving} onClick={handleSave}>
              {editing ? 'Save changes' : 'Create'}
            </Button>
          </>
        }
      >
        <div className={styles.modalForm}>
          <Input
            label="Name"
            id="tmpl-name"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            placeholder="Invoice Extractor"
            required
          />
          <Input
            label="Description (optional)"
            id="tmpl-desc"
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            placeholder="Extracts key fields from invoice documents"
          />
          <Textarea
            label="JSON Schema"
            id="tmpl-schema"
            value={form.schema}
            onChange={(e) => { setForm((f) => ({ ...f, schema: e.target.value })); setSchemaError('') }}
            style={{ minHeight: 260, fontFamily: "'JetBrains Mono', monospace", fontSize: 'var(--text-sm)' }}
            error={schemaError}
            hint='Top-level keys become the extracted fields. E.g. {"invoice_number": "string", "total": "number"}'
          />
        </div>
      </Modal>
    </div>
  )
}
