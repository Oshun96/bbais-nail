import { useCallback, useEffect, useState } from 'react'
import { useShop, useMoney } from '../ShopContext'
import { admin } from './adminApi'

/** Client CRM: history, spend, colour memory, and the shop's own notes. */
export default function Clients({ onError }) {
  const { shop, slug } = useShop()
  const money = useMoney()
  const [q, setQ] = useState('')
  const [list, setList] = useState([])
  const [profile, setProfile] = useState(null)
  const [record, setRecord] = useState({ notes: '', preferences: '', allergies: '' })
  const [saved, setSaved] = useState('')

  const search = useCallback(async (term) => {
    try { setList(await admin(`/api/shops/${shop.slug}/admin/clients?q=${encodeURIComponent(term)}`)) }
    catch (e) { onError(e) }
  }, [shop.slug, onError])

  useEffect(() => { search('') }, [search])

  async function openClient(key) {
    setSaved('')
    try {
      const p = await admin(`/api/shops/${shop.slug}/admin/clients/${key}`)
      setProfile(p)
      setRecord({ notes: p.record.notes || '', preferences: p.record.preferences || '',
                  allergies: p.record.allergies || '' })
    } catch (e) { onError(e) }
  }

  async function save() {
    try {
      await admin(`/api/shops/${shop.slug}/admin/clients/${profile.client_key}`,
                  { method: 'PUT', body: record })
      setSaved('Saved.')
    } catch (e) { onError(e) }
  }

  // Rebooking is just the public flow, pre-filled — one booking path, not two.
  const rebookHref = (h) => {
    const p = new URLSearchParams()
    if (slug) p.set('shop', slug)
    if (h?.service_id) p.set('service', h.service_id)
    return `/book?${p}`
  }

  return (
    <div className="ad-split">
      <div>
        <div className="ad-bar">
          <input placeholder="Search name or phone" value={q}
                 onChange={(e) => { setQ(e.target.value); search(e.target.value) }} />
        </div>
        {list.length === 0 && <p className="muted">Nobody yet.</p>}
        {list.map((c) => (
          <button key={c.client_key} className="ad-clientrow" onClick={() => openClient(c.client_key)}>
            <strong>{c.name || 'Unnamed'}</strong>
            <span className="muted">{c.phone} · {c.visits} visit{c.visits === 1 ? '' : 's'}
              {c.upcoming > 0 && ` · ${c.upcoming} upcoming`}</span>
            <span className="muted" style={{ fontSize: '0.74rem' }}>
              Last: {c.last_service || '—'} on {c.last_date}
            </span>
          </button>
        ))}
      </div>

      <div>
        {!profile && <p className="muted">Pick someone to see their history.</p>}
        {profile && (
          <div className="card">
            <span className="eyebrow">{profile.name}</span>
            <p className="muted" style={{ margin: '6px 0 14px' }}>{profile.phone}{profile.email ? ` · ${profile.email}` : ''}</p>

            <div className="ad-stats">
              <div><span className="k">Visits</span>{profile.summary.visits}</div>
              <div><span className="k">Spend</span>{money(profile.summary.total_spend)}</div>
              <div><span className="k">Average</span>{money(profile.summary.average_ticket)}</div>
              <div><span className="k">Usual tech</span>{profile.summary.usual_technician || '—'}</div>
              <div><span className="k">Usual shape</span>{profile.summary.usual_shape || '—'}</div>
              <div><span className="k">Last in</span>{profile.summary.last_visit || '—'}</div>
            </div>

            {profile.colour_memory.length > 0 && (
              <>
                <hr className="rule" style={{ margin: '16px 0' }} />
                <span className="bk-label">Colour memory — what she actually had</span>
                <div className="ad-colours">
                  {profile.colour_memory.map((c) => (
                    <div key={c.id} className="ad-colour" title={`${c.name} · ${c.on} · ${c.last_had}`}>
                      <span className="sw" style={{ background: c.hex }} />
                      <span>{c.name}<br /><span className="muted" style={{ fontSize: '0.7rem' }}>{c.last_had}</span></span>
                    </div>
                  ))}
                </div>
              </>
            )}

            <hr className="rule" style={{ margin: '16px 0' }} />
            <span className="bk-label">Shop notes</span>
            <div className="bk-fields">
              <label className="wide"><span className="bk-label">Notes</span>
                <textarea rows="2" value={record.notes}
                          onChange={(e) => setRecord({ ...record, notes: e.target.value })} /></label>
              <label><span className="bk-label">Preferences</span>
                <input value={record.preferences}
                       onChange={(e) => setRecord({ ...record, preferences: e.target.value })} /></label>
              <label><span className="bk-label">Allergies</span>
                <input value={record.allergies}
                       onChange={(e) => setRecord({ ...record, allergies: e.target.value })} /></label>
            </div>
            <button className="ad-primary" style={{ marginTop: 10 }} onClick={save}>Save notes</button>
            {saved && <span style={{ color: 'var(--accent)', marginLeft: 12 }}>{saved}</span>}

            <hr className="rule" style={{ margin: '16px 0' }} />
            <span className="bk-label">Visit history</span>
            {profile.history.map((h) => (
              <div key={h.reference} className="bk-line">
                <span>{h.date} · {h.service}<br />
                  <span className="muted" style={{ fontSize: '0.74rem' }}>
                    {h.technician} · {h.reference} · {h.status}
                  </span>
                </span>
                <span>{h.total ? money(h.total) : '—'}</span>
              </div>
            ))}
            <a className="ad-primary" style={{ display: 'inline-block', marginTop: 12, textDecoration: 'none' }}
               href={rebookHref(profile.history[0])}>
              Rebook this client
            </a>
          </div>
        )}
      </div>
    </div>
  )
}
