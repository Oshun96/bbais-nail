import { useEffect, useState } from 'react'
import { useShop, fmtDuration } from '../ShopContext'
import { apiUrl, apiGet } from '../api'

/**
 * The kiosk: check in for an appointment, or join the walk-in line.
 *
 * A waiting client keeps their reference and can watch their own position from
 * their phone — the same queue the front desk sees, not a separate copy.
 */
export default function CheckIn() {
  const { shop } = useShop()
  const [mode, setMode] = useState(null)          // 'appt' | 'walkin'
  const [ref, setRef] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [checkedIn, setCheckedIn] = useState(null)
  const [ticket, setTicket] = useState(null)      // our place in the queue
  const [form, setForm] = useState({ service: '', name: '', phone: '', technician: '' })

  const services = shop.services.filter((s) => s.active && !s.addon)

  // While waiting, keep our position honest without the client refreshing.
  useEffect(() => {
    if (!ticket?.reference) return
    const id = setInterval(async () => {
      try {
        const t = await apiGet(`/api/shops/${shop.slug}/queue/${ticket.reference}`)
        setTicket(t)
      } catch { /* keep the last known position rather than blanking it */ }
    }, 20000)
    return () => clearInterval(id)
  }, [shop.slug, ticket?.reference])

  async function post(path, body) {
    const res = await fetch(apiUrl(path), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'That did not work.')
    return data
  }

  async function checkInAppointment(e) {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      setCheckedIn(await post(`/api/shops/${shop.slug}/bookings/${ref.trim().toUpperCase()}/check-in`))
    } catch (err) { setError(String(err.message)) } finally { setBusy(false) }
  }

  async function joinQueue(e) {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      setTicket(await post(`/api/shops/${shop.slug}/queue`, {
        service: form.service, name: form.name, phone: form.phone,
        technician: form.technician || null,
      }))
    } catch (err) { setError(String(err.message)) } finally { setBusy(false) }
  }

  // ------------------------------------------------------------- in line ---
  if (ticket) {
    return (
      <section className="section" style={{ borderTop: 0 }}>
        <div className="wrap" style={{ maxWidth: 620, textAlign: 'center' }}>
          <span className="eyebrow">You're in line</span>
          <div className="q-pos">{ticket.position}</div>
          <p className="muted">
            {ticket.position === 1
              ? "You're next up."
              : `${ticket.position - 1} ahead of you.`}
            {ticket.estimated_wait_min > 0 && ` About ${fmtDuration(ticket.estimated_wait_min)}.`}
          </p>
          <div className="card raised" style={{ marginTop: 26, textAlign: 'left' }}>
            <div className="bk-line"><span>Reference</span><span>{ticket.reference}</span></div>
            <div className="bk-line"><span>For</span><span>{ticket.service_name}</span></div>
            <div className="bk-line"><span>Name</span><span>{ticket.client?.name}</span></div>
          </div>
          <p className="muted" style={{ marginTop: 18, fontSize: '0.86rem' }}>
            Keep this open — your place updates on its own.
          </p>
        </div>
      </section>
    )
  }

  // ---------------------------------------------------------- checked in ---
  if (checkedIn) {
    return (
      <section className="section" style={{ borderTop: 0 }}>
        <div className="wrap" style={{ maxWidth: 620, textAlign: 'center' }}>
          <span className="eyebrow">Checked in</span>
          <h2 style={{ margin: '12px 0' }}>Thanks, {checkedIn.client?.name?.split(' ')[0] || 'you'}.</h2>
          <p className="muted">
            {checkedIn.technician_name} has you at {checkedIn.start}. Have a seat — someone will
            come get you.
          </p>
          <div className="card raised" style={{ marginTop: 24, textAlign: 'left' }}>
            <div className="bk-line"><span>Reference</span><span>{checkedIn.reference}</span></div>
            <div className="bk-line"><span>Service</span><span>{checkedIn.quote?.service_name}</span></div>
            <div className="bk-line"><span>With</span><span>{checkedIn.technician_name}</span></div>
          </div>
        </div>
      </section>
    )
  }

  // --------------------------------------------------------------- kiosk ---
  return (
    <section className="section" style={{ borderTop: 0 }}>
      <div className="wrap" style={{ maxWidth: 760 }}>
        <div className="section-head">
          <div>
            <span className="eyebrow">Check in</span>
            <h2>Welcome to {shop.name}</h2>
            <p>Booked with us, or just walked in?</p>
          </div>
        </div>

        {!mode && (
          <div className="bk-choices">
            <button className="bk-choice" onClick={() => setMode('appt')}>
              <strong>I have an appointment</strong>
              <span className="muted">Check in with your reference</span>
            </button>
            <button className="bk-choice" onClick={() => setMode('walkin')}>
              <strong>I'm a walk-in</strong>
              <span className="muted">Join the line and see your wait</span>
            </button>
          </div>
        )}

        {mode === 'appt' && (
          <form onSubmit={checkInAppointment} className="card">
            <span className="bk-label">Booking reference</span>
            <input className="q-ref" value={ref} maxLength={6} autoFocus
                   onChange={(e) => setRef(e.target.value.toUpperCase())}
                   placeholder="ABC123" />
            {error && <p className="bk-error">{error}</p>}
            <button className="bk-submit" disabled={ref.trim().length < 4 || busy}>
              {busy ? 'Checking you in…' : 'Check in'}
            </button>
            <button type="button" className="q-back" onClick={() => { setMode(null); setError('') }}>Back</button>
          </form>
        )}

        {mode === 'walkin' && (
          <form onSubmit={joinQueue} className="card">
            <span className="bk-label">What are you here for?</span>
            <div className="bk-choices tight" style={{ marginBottom: 20 }}>
              {services.map((s) => (
                <button key={s.id} type="button"
                        className={`bk-choice${form.service === s.id ? ' on' : ''}`}
                        onClick={() => setForm({ ...form, service: s.id })}>
                  <strong>{s.name}</strong>
                  <span className="muted">{fmtDuration(s.duration_min)}</span>
                </button>
              ))}
            </div>

            <span className="bk-label">Anyone in particular?</span>
            <div className="bk-choices tight" style={{ marginBottom: 20 }}>
              <button type="button" className={`bk-choice${!form.technician ? ' on' : ''}`}
                      onClick={() => setForm({ ...form, technician: '' })}>
                <strong>Whoever's free</strong>
              </button>
              {shop.technicians.filter((t) => t.active).map((t) => (
                <button key={t.id} type="button"
                        className={`bk-choice${form.technician === t.id ? ' on' : ''}`}
                        onClick={() => setForm({ ...form, technician: t.id })}>
                  <strong>{t.name}</strong>
                </button>
              ))}
            </div>

            <div className="bk-fields">
              <label>
                <span className="bk-label">Name</span>
                <input value={form.name} required onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </label>
              <label>
                <span className="bk-label">Phone</span>
                <input value={form.phone} required inputMode="tel"
                       onChange={(e) => setForm({ ...form, phone: e.target.value })} />
              </label>
            </div>

            {error && <p className="bk-error">{error}</p>}
            <button className="bk-submit" disabled={!form.service || !form.name || !form.phone || busy}>
              {busy ? 'Joining…' : 'Join the line'}
            </button>
            <button type="button" className="q-back" onClick={() => { setMode(null); setError('') }}>Back</button>
          </form>
        )}
      </div>
    </section>
  )
}
