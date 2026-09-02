import { useCallback, useEffect, useMemo, useState } from 'react'
import { useShop, useMoney, fmtTime, fmtDuration } from '../ShopContext'
import { apiUrl, apiGet } from '../api'
import { inkOn } from '../theme'

/**
 * The field-based booking flow: the instant, non-technical path.
 *
 * Every price and every open time comes from the API, never from arithmetic
 * done here — the same quote and availability endpoints the front-desk agent
 * will call in Phase 5, so the form and the chat can never disagree.
 */

const STEPS = ['Service', 'Look', 'Colour', 'Technician', 'Time', 'Details', 'Confirm']

function Step({ n, title, blurb, children }) {
  return (
    <section className="bk-step">
      <header>
        <span className="bk-n">{n}</span>
        <div>
          <h3>{title}</h3>
          {blurb && <p className="muted">{blurb}</p>}
        </div>
      </header>
      <div className="bk-body">{children}</div>
    </section>
  )
}

function Choice({ active, onClick, children, disabled }) {
  return (
    <button
      type="button"
      className={`bk-choice${active ? ' on' : ''}`}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  )
}

export default function Book() {
  const { shop, slug } = useShop()
  const money = useMoney()
  const shopParam = slug ? `&shop=${encodeURIComponent(slug)}` : ''

  const services = shop.services.filter((s) => s.active && !s.addon)
  const addons = shop.services.filter((s) => s.active && s.addon)
  const { shapes, lengths, finishes } = shop.nail_menu

  // A consultation (or a rebook from the CRM) hands its choices over in the
  // URL, so the client lands on the form with them already filled in.
  const params = new URLSearchParams(window.location.search)
  const [sel, setSel] = useState(() => ({
    service: params.get('service') || '',
    shape: params.get('shape') || '',
    length: params.get('length') || '',
    finish: params.get('finish') || '',
    colour: params.get('colour') || '',
    technician: params.get('technician') || '',
  }))
  const [prefilled] = useState(() =>
    ['shape', 'length', 'finish', 'colour'].some((k) => params.get(k)))
  const [client, setClient] = useState({ name: '', phone: '', email: '', notes: '' })
  const [quote, setQuote] = useState(null)
  const [days, setDays] = useState([])
  const [date, setDate] = useState('')
  const [slots, setSlots] = useState(null)
  const [time, setTime] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [booked, setBooked] = useState(null)

  const set = (k, v) => {
    setSel((p) => ({ ...p, [k]: v }))
    if (k !== 'colour') { setDate(''); setTime(''); setSlots(null) }
  }

  const optQuery = useMemo(() => {
    const p = new URLSearchParams()
    if (sel.service) p.set('service', sel.service)
    for (const k of ['shape', 'length', 'finish', 'colour']) if (sel[k]) p.set(k, sel[k])
    return p.toString()
  }, [sel])

  // Live quote: price and chair time update as the look is chosen.
  useEffect(() => {
    if (!sel.service) { setQuote(null); return }
    let live = true
    apiGet(`/api/shops/${shop.slug}/quote?${optQuery}`)
      .then((q) => live && setQuote(q))
      .catch(() => live && setQuote(null))
    return () => { live = false }
  }, [shop.slug, sel.service, optQuery])

  // Which days actually have room for THIS selection.
  useEffect(() => {
    if (!sel.service) { setDays([]); return }
    let live = true
    const p = new URLSearchParams({ service: sel.service, days: '14' })
    for (const k of ['shape', 'length', 'finish']) if (sel[k]) p.set(k, sel[k])
    if (sel.technician) p.set('technician', sel.technician)
    apiGet(`/api/shops/${shop.slug}/availability/days?${p}`)
      .then((r) => live && setDays(r.days || []))
      .catch(() => live && setDays([]))
    return () => { live = false }
  }, [shop.slug, sel.service, sel.shape, sel.length, sel.finish, sel.technician])

  const loadSlots = useCallback(
    (d) => {
      const p = new URLSearchParams({ service: sel.service, date: d })
      for (const k of ['shape', 'length', 'finish'] ) if (sel[k]) p.set(k, sel[k])
      if (sel.technician) p.set('technician', sel.technician)
      setSlots(null)
      apiGet(`/api/shops/${shop.slug}/availability?${p}`).then(setSlots).catch(() => setSlots({ slots: [] }))
    },
    [shop.slug, sel]
  )

  const pickDate = (d) => { setDate(d); setTime(''); loadSlots(d) }

  const canSubmit =
    sel.service && date && time && client.name.trim() && client.phone.trim() && !busy

  async function submit(e) {
    e.preventDefault()
    if (!canSubmit) return
    setBusy(true); setError('')
    try {
      const res = await fetch(apiUrl(`/api/shops/${shop.slug}/bookings`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          service: sel.service,
          date, start: time,
          shape: sel.shape || null, length: sel.length || null,
          finish: sel.finish || null, colour: sel.colour || null,
          technician: sel.technician || null,
          ...client,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'That booking could not be completed.')
      setBooked(data)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (err) {
      setError(String(err.message || err))
      // The slot may have gone while the form was open — refresh what's left.
      if (date) loadSlots(date)
    } finally {
      setBusy(false)
    }
  }

  // ------------------------------------------------------------ confirmed ---
  if (booked) {
    const tech = shop.technicians.find((t) => t.id === booked.technician_id)
    return (
      <section className="section" style={{ borderTop: 0 }}>
        <div className="wrap" style={{ maxWidth: 760 }}>
          <span className="eyebrow">You're booked</span>
          <h2 style={{ margin: '10px 0 6px' }}>{booked.reference}</h2>
          <p className="muted">Keep that reference — it's how we find you.</p>

          <div className="card raised" style={{ marginTop: 24 }}>
            <div className="bk-line"><span>Service</span><span>{booked.quote.service_name}</span></div>
            <div className="bk-line"><span>When</span><span>
              {new Date(booked.date + 'T00:00:00').toLocaleDateString(undefined,
                { weekday: 'long', month: 'long', day: 'numeric' })} · {fmtTime(booked.start)}
            </span></div>
            <div className="bk-line"><span>Chair time</span><span>
              {fmtDuration(booked.duration_min)}
              {booked.buffer_min > 0 && ` (+${booked.buffer_min} min processing held)`}
            </span></div>
            <div className="bk-line"><span>With</span><span>
              {tech?.name || booked.technician_name}
              {!booked.tech_was_chosen && ' — assigned for you'}
            </span></div>
            <div className="bk-line"><span>Total</span><span>{money(booked.price)}</span></div>
            {booked.deposit.due > 0 && (
              <div className="bk-line"><span>Deposit</span><span>
                {money(booked.deposit.due)} — settled at the shop
              </span></div>
            )}
          </div>

          {booked.deposit.due > 0 && (
            <p className="muted" style={{ marginTop: 18, fontSize: '0.9rem' }}>
              {shop.deposit.policy_text}
            </p>
          )}

          <button className="bk-submit" style={{ marginTop: 26 }}
                  onClick={() => { setBooked(null); setSel({ service: '', shape: '', length: '', finish: '', colour: '', technician: '' }); setClient({ name: '', phone: '', email: '', notes: '' }); setDate(''); setTime('') }}>
            Book another appointment
          </button>
        </div>
      </section>
    )
  }

  // ----------------------------------------------------------------- form ---
  const needsLook = quote && (shapes.length || lengths.length || finishes.length) &&
    !['Pedicure', 'Add-on'].includes(quote.category)

  return (
    <section className="section" style={{ borderTop: 0 }}>
      <div className="wrap">
        <div className="section-head">
          <div>
            <span className="eyebrow">Book</span>
            <h2>Get on the book</h2>
            <p>
              Times shown are real openings that already account for processing time, so what you
              pick is what you get.
            </p>
          </div>
        </div>

        <div className="bk-grid">
          <form onSubmit={submit} className="bk-main">
            {prefilled && (
              <p className="cs-prefilled">
                We've carried your consultation choices over — change anything you like.
              </p>
            )}

            <Step n="1" title="Choose your service">
              <div className="bk-choices">
                {services.map((s) => (
                  <Choice key={s.id} active={sel.service === s.id} onClick={() => set('service', s.id)}>
                    <strong>{s.name}</strong>
                    <span className="muted">{fmtDuration(s.duration_min)} · {money(s.price)}</span>
                  </Choice>
                ))}
              </div>
              {addons.length > 0 && (
                <p className="muted" style={{ fontSize: '0.84rem', marginTop: 14, marginBottom: 0 }}>
                  Add-ons ({addons.map((a) => a.name).join(', ')}) are added at the chair.
                </p>
              )}
            </Step>

            {sel.service && needsLook && (
              <Step n="2" title="Shape, length and finish"
                    blurb="Specialty work costs more and takes longer — both are shown before you commit.">
                {[['shape', 'Shape', shapes], ['length', 'Length', lengths], ['finish', 'Finish', finishes]]
                  .filter(([, , opts]) => opts.length > 0)
                  .map(([key, label, opts]) => (
                    <div key={key} className="bk-optgroup">
                      <span className="bk-label">{label}</span>
                      <div className="bk-choices tight">
                        {opts.filter((o) => o.active).map((o) => (
                          <Choice key={o.id} active={sel[key] === o.id} onClick={() => set(key, sel[key] === o.id ? '' : o.id)}>
                            <strong>{o.label}</strong>
                            <span className="muted">
                              {o.surcharge > 0 ? `+${money(o.surcharge)}` : 'Included'}
                              {o.extra_min > 0 && ` · +${o.extra_min} min`}
                            </span>
                          </Choice>
                        ))}
                      </div>
                    </div>
                  ))}
              </Step>
            )}

            {sel.service && (
              <Step n={needsLook ? '3' : '2'} title="Pick your colour" blurb="Or leave it and decide at the chair.">
                <div className="bk-swatches">
                  {shop.colours.filter((c) => c.active).map((c) => (
                    <button key={c.id} type="button"
                            className={`bk-sw${sel.colour === c.id ? ' on' : ''}`}
                            onClick={() => set('colour', sel.colour === c.id ? '' : c.id)}
                            title={`${c.name} · ${c.family}`}>
                      <span className="bk-chip" style={{ background: c.hex, color: inkOn(c.hex) }}>
                        {sel.colour === c.id ? '✓' : ''}
                      </span>
                      <span className="bk-swname">{c.name}</span>
                    </button>
                  ))}
                </div>
              </Step>
            )}

            {sel.service && (
              <Step n={needsLook ? '4' : '3'} title="Who's doing your nails?">
                <div className="bk-choices">
                  <Choice active={!sel.technician} onClick={() => set('technician', '')}>
                    <strong>No preference</strong>
                    <span className="muted">Whoever is free — usually the soonest appointment</span>
                  </Choice>
                  {shop.technicians.filter((t) => t.active).map((t) => (
                    <Choice key={t.id} active={sel.technician === t.id} onClick={() => set('technician', t.id)}>
                      <strong>{t.name}</strong>
                      <span className="muted">{t.specialties.slice(0, 3).join(' · ') || t.title}</span>
                    </Choice>
                  ))}
                </div>
              </Step>
            )}

            {sel.service && (
              <Step n={needsLook ? '5' : '4'} title="Pick a day and time">
                <div className="bk-days">
                  {days.map((d) => {
                    const dt = new Date(d.date + 'T00:00:00')
                    const disabled = d.count === 0
                    return (
                      <button key={d.date} type="button" disabled={disabled}
                              className={`bk-day${date === d.date ? ' on' : ''}`}
                              onClick={() => pickDate(d.date)}>
                        <span className="dow">{dt.toLocaleDateString(undefined, { weekday: 'short' })}</span>
                        <span className="dom">{dt.getDate()}</span>
                        <span className="cnt">{disabled ? (d.open ? 'Full' : 'Closed') : `${d.count} open`}</span>
                      </button>
                    )
                  })}
                </div>

                {date && (
                  <div className="bk-times">
                    {slots === null && <span className="muted">Finding open times…</span>}
                    {slots && slots.slots.length === 0 && (
                      <span className="muted">Nothing left that day{slots.closed_reason ? ` — ${slots.closed_reason}` : ''}.</span>
                    )}
                    {slots && slots.slots.map((t) => (
                      <Choice key={t} active={time === t} onClick={() => setTime(t)}>
                        <strong>{fmtTime(t)}</strong>
                      </Choice>
                    ))}
                  </div>
                )}
              </Step>
            )}

            {time && (
              <Step n={needsLook ? '6' : '5'} title="Your details">
                <div className="bk-fields">
                  <label>
                    <span className="bk-label">Name *</span>
                    <input value={client.name} required
                           onChange={(e) => setClient({ ...client, name: e.target.value })} />
                  </label>
                  <label>
                    <span className="bk-label">Phone *</span>
                    <input value={client.phone} required inputMode="tel"
                           onChange={(e) => setClient({ ...client, phone: e.target.value })} />
                  </label>
                  <label>
                    <span className="bk-label">Email</span>
                    <input value={client.email} type="email"
                           onChange={(e) => setClient({ ...client, email: e.target.value })} />
                  </label>
                  <label className="wide">
                    <span className="bk-label">Anything we should know?</span>
                    <textarea rows="3" value={client.notes}
                              onChange={(e) => setClient({ ...client, notes: e.target.value })} />
                  </label>
                </div>

                {error && <p className="bk-error">{error}</p>}

                <button className="bk-submit" type="submit" disabled={!canSubmit}>
                  {busy ? 'Confirming…' : quote?.deposit_due
                    ? `Confirm — ${money(quote.deposit_due)} deposit due at the shop`
                    : 'Confirm booking'}
                </button>
              </Step>
            )}
          </form>

          {/* Running summary — always shows what it costs and how long it takes. */}
          <aside className="bk-summary">
            <div className="card raised">
              <span className="eyebrow">Your appointment</span>
              {!quote && <p className="muted" style={{ marginTop: 14, marginBottom: 0 }}>Choose a service to begin.</p>}
              {quote && (
                <>
                  <div style={{ marginTop: 14 }}>
                    {quote.lines.map((li, i) => (
                      <div key={i} className="bk-line">
                        <span>{li.label}<br /><span className="muted" style={{ fontSize: '0.76rem' }}>{li.detail}</span></span>
                        <span>{li.amount > 0 ? money(li.amount) : '—'}</span>
                      </div>
                    ))}
                  </div>
                  <hr className="rule" style={{ margin: '14px 0' }} />
                  <div className="bk-line total"><span>Total</span><span>{money(quote.price)}</span></div>
                  <div className="bk-line"><span className="muted">In the chair</span><span className="muted">{fmtDuration(quote.duration_min)}</span></div>
                  {quote.buffer_min > 0 && (
                    <div className="bk-line"><span className="muted">Processing held</span><span className="muted">{quote.buffer_min} min</span></div>
                  )}
                  <div className="bk-line"><span className="muted">Booked as</span><span className="muted">{fmtDuration(quote.block_min)}</span></div>
                  {quote.deposit_due > 0 && (
                    <>
                      <hr className="rule" style={{ margin: '14px 0' }} />
                      <div className="bk-line"><span>Deposit to hold</span><span style={{ color: 'var(--accent)' }}>{money(quote.deposit_due)}</span></div>
                      <p className="muted" style={{ fontSize: '0.78rem', margin: '8px 0 0' }}>
                        Settled at the shop and credited to your total. Free to change up to{' '}
                        {shop.deposit.refundable_until_hours} hours ahead.
                      </p>
                    </>
                  )}
                  {date && time && (
                    <p style={{ marginTop: 16, marginBottom: 0, color: 'var(--accent)' }}>
                      {new Date(date + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })} at {fmtTime(time)}
                    </p>
                  )}
                </>
              )}
            </div>
          </aside>
        </div>
      </div>
    </section>
  )
}
