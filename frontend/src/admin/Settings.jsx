import { useState } from 'react'
import { useShop, useMoney } from '../ShopContext'
import { admin } from './adminApi'
import { DAY_LABELS_FALLBACK } from './days'

/**
 * Editing the shop itself: services, technicians' days, hours, deposit rules.
 *
 * Every save goes through the same schema that validates a seed file, so a bad
 * edit is refused rather than reaching the storefront — including the dark-luxe
 * rule that a shop cannot ship a white background.
 */
export default function Settings({ onError, onSaved }) {
  const { shop } = useShop()
  const money = useMoney()
  const [services, setServices] = useState(() => shop.services.map((s) => ({ ...s })))
  const [hours, setHours] = useState(() => ({ ...shop.hours }))
  const [deposit, setDeposit] = useState(() => ({ ...shop.deposit }))
  const [booking, setBooking] = useState(() => ({ ...shop.booking }))
  const [msg, setMsg] = useState('')

  const days = shop.derived?.day_order || Object.keys(DAY_LABELS_FALLBACK)
  const labels = shop.derived?.day_labels || DAY_LABELS_FALLBACK

  async function save(patch, what) {
    setMsg('')
    try {
      await admin(`/api/shops/${shop.slug}/admin/config`, { method: 'PATCH', body: patch })
      setMsg(`${what} saved — live on the site now.`)
      onSaved?.()
    } catch (e) { onError(e) }
  }

  const setSvc = (i, k, v) =>
    setServices((p) => p.map((s, j) => (j === i ? { ...s, [k]: v } : s)))

  return (
    <div>
      {msg && <p style={{ color: 'var(--accent)' }}>{msg}</p>}

      <div className="card" style={{ marginBottom: 18 }}>
        <span className="eyebrow">Services</span>
        <p className="muted" style={{ fontSize: '0.82rem', marginTop: 8 }}>
          Buffer is the processing time held after the service — it is what stops the next
          client landing on a set that is still curing.
        </p>
        <div className="ad-table">
          <div className="ad-th"><span>Service</span><span>Price</span><span>Minutes</span><span>Buffer</span><span>Live</span></div>
          {services.map((s, i) => (
            <div key={s.id} className="ad-tr">
              <span>{s.name}<br /><span className="muted" style={{ fontSize: '0.72rem' }}>{s.category}</span></span>
              <input type="number" step="1" value={s.price} onChange={(e) => setSvc(i, 'price', Number(e.target.value))} />
              <input type="number" step="5" value={s.duration_min} onChange={(e) => setSvc(i, 'duration_min', Number(e.target.value))} />
              <input type="number" step="5" value={s.buffer_min} onChange={(e) => setSvc(i, 'buffer_min', Number(e.target.value))} />
              <input type="checkbox" checked={s.active} onChange={(e) => setSvc(i, 'active', e.target.checked)} />
            </div>
          ))}
        </div>
        <button className="ad-primary" style={{ marginTop: 12 }} onClick={() => save({ services }, 'Services')}>
          Save services
        </button>
      </div>

      <div className="card" style={{ marginBottom: 18 }}>
        <span className="eyebrow">Opening hours</span>
        {days.map((d) => (
          <div key={d} className="ad-hours">
            <span>{labels[d]}</span>
            <label className="ad-check">
              <input type="checkbox" checked={!hours[d]?.closed}
                     onChange={(e) => setHours({ ...hours, [d]: { ...hours[d], closed: !e.target.checked } })} />
              Open
            </label>
            <input type="time" value={hours[d]?.open || '09:00'} disabled={hours[d]?.closed}
                   onChange={(e) => setHours({ ...hours, [d]: { ...hours[d], open: e.target.value } })} />
            <input type="time" value={hours[d]?.close || '19:00'} disabled={hours[d]?.closed}
                   onChange={(e) => setHours({ ...hours, [d]: { ...hours[d], close: e.target.value } })} />
          </div>
        ))}
        <button className="ad-primary" style={{ marginTop: 12 }} onClick={() => save({ hours }, 'Hours')}>
          Save hours
        </button>
      </div>

      <div className="card" style={{ marginBottom: 18 }}>
        <span className="eyebrow">Deposit rules</span>
        <div className="bk-fields" style={{ marginTop: 12 }}>
          <label className="ad-check" style={{ alignSelf: 'end' }}>
            <input type="checkbox" checked={deposit.enabled}
                   onChange={(e) => setDeposit({ ...deposit, enabled: e.target.checked })} />
            Take deposits
          </label>
          <label><span className="bk-label">Kind</span>
            <select value={deposit.kind} onChange={(e) => setDeposit({ ...deposit, kind: e.target.value })}>
              <option value="percent">Percent of the service</option>
              <option value="fixed">Flat amount</option>
            </select></label>
          <label><span className="bk-label">{deposit.kind === 'percent' ? 'Percent' : 'Amount'}</span>
            <input type="number" step="1" value={deposit.amount}
                   onChange={(e) => setDeposit({ ...deposit, amount: Number(e.target.value) })} /></label>
          <label><span className="bk-label">Applies to bookings over (min)</span>
            <input type="number" step="15" value={deposit.applies_over_min}
                   onChange={(e) => setDeposit({ ...deposit, applies_over_min: Number(e.target.value) })} /></label>
          <label><span className="bk-label">Refundable until (hours before)</span>
            <input type="number" step="1" value={deposit.refundable_until_hours}
                   onChange={(e) => setDeposit({ ...deposit, refundable_until_hours: Number(e.target.value) })} /></label>
          <label className="wide"><span className="bk-label">Policy shown to clients</span>
            <textarea rows="2" value={deposit.policy_text}
                      onChange={(e) => setDeposit({ ...deposit, policy_text: e.target.value })} /></label>
        </div>
        <button className="ad-primary" style={{ marginTop: 12 }} onClick={() => save({ deposit }, 'Deposit rules')}>
          Save deposit rules
        </button>
      </div>

      <div className="card">
        <span className="eyebrow">Booking rules</span>
        <div className="bk-fields" style={{ marginTop: 12 }}>
          <label><span className="bk-label">Slot granularity (min)</span>
            <input type="number" step="5" value={booking.slot_granularity_min}
                   onChange={(e) => setBooking({ ...booking, slot_granularity_min: Number(e.target.value) })} /></label>
          <label><span className="bk-label">Book closes (min before)</span>
            <input type="number" step="15" value={booking.min_lead_min}
                   onChange={(e) => setBooking({ ...booking, min_lead_min: Number(e.target.value) })} /></label>
          <label><span className="bk-label">Book opens (days ahead)</span>
            <input type="number" step="1" value={booking.max_days_ahead}
                   onChange={(e) => setBooking({ ...booking, max_days_ahead: Number(e.target.value) })} /></label>
          <label><span className="bk-label">Remind (hours before)</span>
            <input type="number" step="1" value={booking.remind_hours_before}
                   onChange={(e) => setBooking({ ...booking, remind_hours_before: Number(e.target.value) })} /></label>
        </div>
        <button className="ad-primary" style={{ marginTop: 12 }} onClick={() => save({ booking }, 'Booking rules')}>
          Save booking rules
        </button>
      </div>
    </div>
  )
}
