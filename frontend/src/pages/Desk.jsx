import { useCallback, useEffect, useState } from 'react'
import { useShop, useMoney, fmtDuration, fmtTime } from '../ShopContext'
import { apiUrl, apiGet } from '../api'
import CardPayment from '../components/CardPayment'

/**
 * The front desk: the live walk-in queue, and ringing a ticket up.
 *
 * Phase 4 gives this a full home (calendar, CRM, manual scheduling). What is
 * here is the working checkout path — every amount computed server-side, and
 * nothing marked paid until the provider confirms it.
 */
export default function Desk() {
  const { shop } = useShop()
  const money = useMoney()

  const [queue, setQueue] = useState(null)
  const [payCfg, setPayCfg] = useState(null)
  const [ref, setRef] = useState('')
  const [booking, setBooking] = useState(null)
  const [addons, setAddons] = useState([])
  const [tipPercent, setTipPercent] = useState(null)
  const [tipFlat, setTipFlat] = useState('')
  const [begun, setBegun] = useState(null)
  const [done, setDone] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const addonList = shop.services.filter((s) => s.active && s.addon)

  const loadQueue = useCallback(() => {
    apiGet(`/api/shops/${shop.slug}/queue`).then(setQueue).catch(() => setQueue(null))
  }, [shop.slug])

  useEffect(() => {
    loadQueue()
    apiGet(`/api/shops/${shop.slug}/payments/status`).then(setPayCfg).catch(() => setPayCfg(null))
    const id = setInterval(loadQueue, 20000)
    return () => clearInterval(id)
  }, [shop.slug, loadQueue])

  async function post(path, body) {
    const res = await fetch(apiUrl(path), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'That did not work.')
    return data
  }

  const tipArgs = () =>
    tipPercent != null ? { tip_percent: tipPercent } : { tip: Number(tipFlat) || 0 }

  async function seat(r) {
    setError('')
    try { await post(`/api/shops/${shop.slug}/queue/${r}/seat`); loadQueue() }
    catch (e) { setError(String(e.message)) }
  }

  async function openTicket(e) {
    e?.preventDefault()
    setError(''); setBusy(true); setDone(null); setBegun(null)
    try {
      const b = await apiGet(`/api/shops/${shop.slug}/bookings/${ref.trim().toUpperCase()}`)
      setBooking(b)
      setBegun(await post(`/api/shops/${shop.slug}/bookings/${b.reference}/checkout/begin`,
                          { addons, ...tipArgs() }))
    } catch (e) { setError(String(e.message)); setBooking(null) }
    finally { setBusy(false) }
  }

  // Re-price whenever the desk adds something or changes the tip.
  useEffect(() => {
    if (!booking) return
    let live = true
    post(`/api/shops/${shop.slug}/bookings/${booking.reference}/checkout/begin`, { addons, ...tipArgs() })
      .then((r) => live && setBegun(r))
      .catch((e) => live && setError(String(e.message)))
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [addons, tipPercent, tipFlat])

  async function settle(extra) {
    setBusy(true); setError('')
    try {
      const r = await post(`/api/shops/${shop.slug}/bookings/${booking.reference}/checkout/settle`, {
        payment_reference: extra?.payment_reference || begun?.payment?.reference || '',
        client_token: extra?.client_token || '',
        method: extra?.method || 'card',
        addons, ...tipArgs(),
      })
      setDone(r); setBooking(null); setBegun(null); setRef(''); setAddons([]); setTipPercent(null); setTipFlat('')
      loadQueue()
    } catch (e) { setError(String(e.message)) } finally { setBusy(false) }
  }

  const t = begun?.ticket

  return (
    <section className="section" style={{ borderTop: 0 }}>
      <div className="wrap">
        <div className="section-head">
          <div>
            <span className="eyebrow">Front desk</span>
            <h2>The floor right now</h2>
          </div>
          {payCfg && (
            <span className="muted" style={{ fontSize: '0.82rem' }}>
              Payments: {payCfg.processor}
              {payCfg.configured ? (payCfg.sandbox ? ' · sandbox' : ' · live') : ' · not switched on'}
            </span>
          )}
        </div>

        <div className="grid two">
          {/* ------------------------------------------------------ queue --- */}
          <div className="card">
            <span className="eyebrow">Walk-in queue</span>
            {!queue && <p className="muted" style={{ marginTop: 14 }}>Loading…</p>}
            {queue && queue.waiting.length === 0 && (
              <p className="muted" style={{ marginTop: 14, marginBottom: 0 }}>Nobody waiting.</p>
            )}
            {queue?.waiting.map((w) => (
              <div key={w.reference} className="q-row">
                <span className="q-num">{w.position}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <strong>{w.client?.name}</strong>
                  <div className="muted" style={{ fontSize: '0.8rem' }}>
                    {w.service_name} · {w.reference}
                    {w.estimated_wait_min > 0 && ` · ~${fmtDuration(w.estimated_wait_min)}`}
                  </div>
                </div>
                <button className="q-seat" onClick={() => seat(w.reference)}>Seat</button>
              </div>
            ))}
            {queue && (
              <p className="muted" style={{ fontSize: '0.78rem', marginTop: 14, marginBottom: 0 }}>
                {queue.technicians_on_floor} technician{queue.technicians_on_floor === 1 ? '' : 's'} on the floor today.
              </p>
            )}
          </div>

          {/* --------------------------------------------------- checkout --- */}
          <div className="card">
            <span className="eyebrow">Check out</span>

            {done && (
              <div style={{ marginTop: 14 }}>
                <p style={{ color: 'var(--accent)' }}>
                  Paid — {money(done.receipt.ticket.total)} · {done.receipt.payment.method}
                  {done.receipt.payment.sandbox ? ' (sandbox)' : ''}
                </p>
                <div className="bk-line"><span>Reference</span><span>{done.receipt.reference}</span></div>
                <div className="bk-line"><span>Client</span><span>{done.receipt.client}</span></div>
                <div className="bk-line"><span>Tip</span><span>{money(done.receipt.ticket.tip)}</span></div>
                <button className="bk-submit" style={{ marginTop: 16 }} onClick={() => setDone(null)}>
                  Next ticket
                </button>
              </div>
            )}

            {!done && !booking && (
              <form onSubmit={openTicket} style={{ marginTop: 14 }}>
                <span className="bk-label">Booking reference</span>
                <input className="q-ref" value={ref} maxLength={6}
                       onChange={(e) => setRef(e.target.value.toUpperCase())} placeholder="ABC123" />
                {error && <p className="bk-error">{error}</p>}
                <button className="bk-submit" disabled={ref.trim().length < 4 || busy}>
                  {busy ? 'Opening…' : 'Open ticket'}
                </button>
              </form>
            )}

            {!done && booking && t && (
              <div style={{ marginTop: 14 }}>
                <div className="bk-line"><span>{booking.client?.name}</span><span>{booking.reference}</span></div>
                <div className="bk-line muted"><span>{booking.technician_name}</span>
                  <span>{fmtTime(booking.start)}</span></div>
                <hr className="rule" style={{ margin: '12px 0' }} />

                <span className="bk-label">Added at the chair</span>
                <div className="bk-choices tight" style={{ marginBottom: 16 }}>
                  {addonList.map((a) => (
                    <button key={a.id} type="button"
                            className={`bk-choice${addons.includes(a.id) ? ' on' : ''}`}
                            onClick={() => setAddons((p) => p.includes(a.id) ? p.filter((x) => x !== a.id) : [...p, a.id])}>
                      <strong>{a.name}</strong>
                      <span className="muted">{money(a.price)}</span>
                    </button>
                  ))}
                </div>

                <span className="bk-label">Tip</span>
                <div className="bk-choices tight" style={{ marginBottom: 16 }}>
                  {(payCfg?.tip_presets || []).map((p) => (
                    <button key={p} type="button" className={`bk-choice${tipPercent === p ? ' on' : ''}`}
                            onClick={() => { setTipPercent(p); setTipFlat('') }}>
                      <strong>{p}%</strong>
                    </button>
                  ))}
                  <button type="button" className={`bk-choice${tipPercent === 0 && !tipFlat ? ' on' : ''}`}
                          onClick={() => { setTipPercent(0); setTipFlat('') }}>
                    <strong>No tip</strong>
                  </button>
                </div>

                {t.lines.map((l, i) => (
                  <div key={i} className="bk-line"><span>{l.label}</span><span>{money(l.amount)}</span></div>
                ))}
                <div className="bk-line muted"><span>Tax</span><span>{money(t.tax)}</span></div>
                <div className="bk-line muted"><span>Tip</span><span>{money(t.tip)}</span></div>
                {t.deposit_credit > 0 && (
                  <div className="bk-line"><span>Deposit already paid</span><span>−{money(t.deposit_credit)}</span></div>
                )}
                <div className="bk-line total"><span>Due</span><span>{money(t.due_now)}</span></div>

                {error && <p className="bk-error">{error}</p>}

                {begun.payment && begun.configured ? (
                  <CardPayment
                    payment={begun.payment}
                    processor={begun.processor}
                    amount={t.due_now}
                    currency={t.currency}
                    onPaid={settle}
                    onError={(e) => setError(String(e.message || e))}
                  />
                ) : (
                  <p className="muted" style={{ fontSize: '0.84rem', marginTop: 14 }}>
                    Card payments aren't switched on for this shop yet — take it at the counter.
                  </p>
                )}

                <button className="bk-submit" style={{ marginTop: 12, background: 'transparent', color: 'var(--text)', border: '1px solid var(--line)' }}
                        disabled={busy} onClick={() => settle({ method: 'cash' })}>
                  {busy ? 'Recording…' : `Take ${money(t.due_now)} at the counter`}
                </button>
                <button type="button" className="q-back" onClick={() => { setBooking(null); setBegun(null); setError('') }}>
                  Cancel
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
