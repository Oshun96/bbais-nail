import { useCallback, useEffect, useState } from 'react'
import { useShop, useMoney, fmtTime, fmtDuration } from '../ShopContext'
import { admin } from './adminApi'

/** The book, by technician, with everything the desk does to a booking. */
export default function Calendar({ onError }) {
  const { shop } = useShop()
  const money = useMoney()
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [cal, setCal] = useState(null)
  const [open, setOpen] = useState(null)      // the booking being worked on
  const [edit, setEdit] = useState({ date: '', start: '', technician: '' })
  const [pay, setPay] = useState({ amount: '', method: 'cash', note: '' })
  const [adding, setAdding] = useState(false)
  const [nb, setNb] = useState({ service: '', technician: '', start: '', name: '', phone: '' })
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    try { setCal(await admin(`/api/shops/${shop.slug}/admin/calendar?date=${date}`)) }
    catch (e) { onError(e) }
  }, [shop.slug, date, onError])

  useEffect(() => { load() }, [load])

  const day = cal?.days?.[0]
  const shift = (n) => {
    const d = new Date(date + 'T00:00:00'); d.setDate(d.getDate() + n)
    setDate(d.toISOString().slice(0, 10)); setOpen(null)
  }

  async function act(fn, ok) {
    setMsg('')
    try { await fn(); setMsg(ok); setOpen(null); load() }
    catch (e) { onError(e) }
  }

  const services = shop.services.filter((s) => s.active && !s.addon)

  return (
    <div>
      <div className="ad-bar">
        <button onClick={() => shift(-1)}>←</button>
        <input type="date" value={date} onChange={(e) => { setDate(e.target.value); setOpen(null) }} />
        <button onClick={() => shift(1)}>→</button>
        <button onClick={() => setDate(new Date().toISOString().slice(0, 10))}>Today</button>
        <span style={{ marginLeft: 'auto' }}>
          <button className="ad-primary" onClick={() => setAdding((v) => !v)}>
            {adding ? 'Close' : '+ New booking'}
          </button>
        </span>
      </div>

      {msg && <p style={{ color: 'var(--accent)' }}>{msg}</p>}

      {adding && (
        <div className="card" style={{ marginBottom: 18 }}>
          <span className="eyebrow">Book from the desk</span>
          <p className="muted" style={{ fontSize: '0.82rem', marginTop: 8 }}>
            Any time inside the tech's shift — the grid and lead time don't apply here.
          </p>
          <div className="bk-fields">
            <label><span className="bk-label">Service</span>
              <select value={nb.service} onChange={(e) => setNb({ ...nb, service: e.target.value })}>
                <option value="">Choose…</option>
                {services.map((s) => <option key={s.id} value={s.id}>{s.name} — {money(s.price)}</option>)}
              </select>
            </label>
            <label><span className="bk-label">Technician</span>
              <select value={nb.technician} onChange={(e) => setNb({ ...nb, technician: e.target.value })}>
                <option value="">Choose…</option>
                {(day?.technicians || []).filter((t) => t.working).map((t) =>
                  <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </label>
            <label><span className="bk-label">Start</span>
              <input type="time" value={nb.start} onChange={(e) => setNb({ ...nb, start: e.target.value })} />
            </label>
            <label><span className="bk-label">Name</span>
              <input value={nb.name} onChange={(e) => setNb({ ...nb, name: e.target.value })} />
            </label>
            <label><span className="bk-label">Phone</span>
              <input value={nb.phone} onChange={(e) => setNb({ ...nb, phone: e.target.value })} />
            </label>
          </div>
          <button className="bk-submit"
                  disabled={!nb.service || !nb.technician || !nb.start || !nb.name || !nb.phone}
                  onClick={() => act(
                    () => admin(`/api/shops/${shop.slug}/admin/bookings`, {
                      method: 'POST', body: { ...nb, date },
                    }),
                    'Booked.')}>
            Add to the book
          </button>
        </div>
      )}

      {!cal && <p className="muted">Loading the book…</p>}

      {day && !day.open && (
        <p className="muted">Closed on {new Date(date + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'long' })}.</p>
      )}

      {day?.open && (
        <div className="ad-cols">
          {day.technicians.map((t) => (
            <div key={t.id} className="ad-col">
              <div className="ad-colhead">
                <strong>{t.name}</strong>
                <span className="muted">{t.working ? `${fmtTime(t.shift.start)}–${fmtTime(t.shift.end)}` : 'Off'}</span>
              </div>
              {t.working && t.bookings.length === 0 && <p className="muted ad-empty">Nothing booked.</p>}
              {t.bookings.map((b) => (
                <button key={b.reference} className={`ad-appt st-${b.status}`} onClick={() => {
                  setOpen(b)
                  setEdit({ date: b.date, start: b.start, technician: b.technician_id })
                  setPay({ amount: String(b.price), method: 'cash', note: '' })
                }}>
                  <span className="t">{fmtTime(b.start)} – {fmtTime(b.end)}</span>
                  <strong>{b.client?.name}</strong>
                  <span className="muted">{b.quote?.service_name}</span>
                  <span className="ad-status">{b.status.replace('_', ' ')}</span>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}

      {open && (
        <div className="ad-panel card">
          <div className="bk-line"><strong>{open.client?.name}</strong>
            <span className="ad-ref">{open.reference}</span></div>
          <div className="bk-line muted"><span>{open.quote?.service_name}</span>
            <span>{fmtDuration(open.duration_min)} + {open.buffer_min} min held</span></div>
          <div className="bk-line muted"><span>{open.client?.phone}</span><span>{money(open.price)}</span></div>
          {open.deposit?.due > 0 && (
            <div className="bk-line muted"><span>Deposit {open.deposit.status}</span><span>{money(open.deposit.due)}</span></div>
          )}
          <hr className="rule" style={{ margin: '14px 0' }} />

          <span className="bk-label">Move it</span>
          <div className="bk-fields">
            <label><span className="bk-label">Date</span>
              <input type="date" value={edit.date} onChange={(e) => setEdit({ ...edit, date: e.target.value })} /></label>
            <label><span className="bk-label">Start</span>
              <input type="time" value={edit.start} onChange={(e) => setEdit({ ...edit, start: e.target.value })} /></label>
            <label><span className="bk-label">Technician</span>
              <select value={edit.technician} onChange={(e) => setEdit({ ...edit, technician: e.target.value })}>
                {shop.technicians.filter((t) => t.active).map((t) =>
                  <option key={t.id} value={t.id}>{t.name}</option>)}
              </select></label>
          </div>
          <button className="ad-primary" style={{ marginTop: 10 }}
                  onClick={() => act(() => admin(`/api/shops/${shop.slug}/admin/bookings/${open.reference}`,
                                                 { method: 'PATCH', body: edit }), 'Moved.')}>
            Save the move
          </button>

          <hr className="rule" style={{ margin: '18px 0' }} />
          <span className="bk-label">Take a payment at the desk</span>
          <div className="bk-fields">
            <label><span className="bk-label">Amount</span>
              <input type="number" step="0.01" value={pay.amount}
                     onChange={(e) => setPay({ ...pay, amount: e.target.value })} /></label>
            <label><span className="bk-label">Method</span>
              <select value={pay.method} onChange={(e) => setPay({ ...pay, method: e.target.value })}>
                <option value="cash">Cash</option>
                <option value="card-terminal">Card on the shop terminal</option>
                <option value="other">Other</option>
              </select></label>
          </div>
          <button className="ad-primary" style={{ marginTop: 10 }}
                  onClick={() => act(() => admin(`/api/shops/${shop.slug}/admin/bookings/${open.reference}/payment`,
                                                 { method: 'POST', body: { amount: Number(pay.amount), method: pay.method, note: pay.note } }),
                                     'Payment recorded and marked complete.')}>
            Record {money(Number(pay.amount) || 0)}
          </button>

          <div className="ad-actions">
            <button onClick={() => act(() => admin(`/api/shops/${shop.slug}/admin/bookings/${open.reference}/complete`,
                                                   { method: 'POST' }), 'Marked complete.')}>
              Mark complete (no charge)
            </button>
            <button onClick={() => setOpen(null)}>Close</button>
          </div>
        </div>
      )}
    </div>
  )
}
