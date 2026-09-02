import { useState } from 'react'
import { useShop } from '../ShopContext'
import { admin, clearKey, getKey, setKey, Unauthorized } from '../admin/adminApi'
import Calendar from '../admin/Calendar'
import Clients from '../admin/Clients'
import Settings from '../admin/Settings'
import Reviews from '../admin/Reviews'

const TABS = [
  ['calendar', 'Calendar'],
  ['clients', 'Clients'],
  ['settings', 'Shop settings'],
  ['reviews', 'Reviews'],
]

export default function Admin() {
  const { shop, refreshShop } = useShop()
  const [authed, setAuthed] = useState(() => Boolean(getKey()))
  const [key, setKeyInput] = useState('')
  const [tab, setTab] = useState('calendar')
  const [error, setError] = useState('')

  // A rejected key logs out rather than leaving the panel half-broken.
  const onError = (e) => {
    if (e instanceof Unauthorized) { clearKey(); setAuthed(false) }
    setError(String(e.message || e))
  }

  async function signIn(e) {
    e.preventDefault()
    setError('')
    setKey(key.trim())
    try {
      await admin(`/api/shops/${shop.slug}/admin/calendar`)
      setAuthed(true); setKeyInput('')
    } catch (err) { clearKey(); setError(err instanceof Unauthorized ? 'That key was not accepted.' : String(err.message)) }
  }

  if (!authed) {
    return (
      <section className="section" style={{ borderTop: 0 }}>
        <div className="wrap" style={{ maxWidth: 420 }}>
          <span className="eyebrow">Staff only</span>
          <h2 style={{ margin: '10px 0 18px' }}>{shop.name}</h2>
          <form onSubmit={signIn} className="card">
            <span className="bk-label">Admin key</span>
            <input type="password" value={key} autoFocus
                   onChange={(e) => setKeyInput(e.target.value)} className="ad-keyin" />
            {error && <p className="bk-error">{error}</p>}
            <button className="bk-submit" disabled={!key.trim()}>Unlock</button>
          </form>
          <p className="muted" style={{ fontSize: '0.8rem', marginTop: 14 }}>
            The key is kept for this tab only and is cleared when the browser closes.
          </p>
        </div>
      </section>
    )
  }

  return (
    <section className="section" style={{ borderTop: 0 }}>
      <div className="wrap">
        <div className="section-head">
          <div>
            <span className="eyebrow">Front desk · admin</span>
            <h2>{shop.name}</h2>
          </div>
          <button className="ad-signout" onClick={() => { clearKey(); setAuthed(false) }}>Sign out</button>
        </div>

        <div className="ad-tabs">
          {TABS.map(([id, label]) => (
            <button key={id} className={tab === id ? 'on' : undefined} onClick={() => { setTab(id); setError('') }}>
              {label}
            </button>
          ))}
        </div>

        {error && <p className="bk-error">{error}</p>}

        {tab === 'calendar' && <Calendar onError={onError} />}
        {tab === 'clients' && <Clients onError={onError} />}
        {tab === 'settings' && <Settings onError={onError} onSaved={refreshShop} />}
        {tab === 'reviews' && <Reviews onError={onError} />}
      </div>
    </section>
  )
}
