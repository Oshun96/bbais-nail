import { useEffect, useRef, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useShop, useMoney } from '../ShopContext'
import { apiUrl, apiGet } from '../api'

/**
 * Photo consultation.
 *
 * A photo of the client's hands comes back as a reading and a recommendation
 * made only from THIS shop's menu — so everything suggested is something the
 * shop can actually do, and it carries straight into the booking form.
 */
export default function Consult() {
  const { shop, slug } = useShop()
  const money = useMoney()
  const nav = useNavigate()
  const loc = useLocation()

  const [status, setStatus] = useState(null)
  const [preview, setPreview] = useState('')
  const [file, setFile] = useState(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [slow, setSlow] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const slowTimer = useRef(null)

  useEffect(() => {
    let live = true
    apiGet(`/api/shops/${shop.slug}/consult/status`)
      .then((s) => live && setStatus(s))
      .catch(() => live && setStatus({ available: false }))
    return () => { live = false }
  }, [shop.slug])

  // Release the object URL rather than leaking one per photo tried.
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])

  function pick(e) {
    const f = e.target.files?.[0]
    if (!f) return
    setError('')
    setResult(null)
    setFile(f)
    if (preview) URL.revokeObjectURL(preview)
    setPreview(URL.createObjectURL(f))
  }

  async function submit() {
    if (!file || busy) return
    setBusy(true); setError(''); setSlow(false)
    slowTimer.current = setTimeout(() => setSlow(true), 8000)
    try {
      const body = new FormData()
      body.append('photo', file)
      // The client's own words lead the recommendation.
      if (note.trim()) body.append('note', note.trim())
      const res = await fetch(apiUrl(`/api/shops/${shop.slug}/consult`), { method: 'POST', body })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'That consultation could not be completed.')
      setResult(data)
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      clearTimeout(slowTimer.current)
      setBusy(false); setSlow(false)
    }
  }

  function bookWithThese() {
    const p = new URLSearchParams()
    const keep = new URLSearchParams(loc.search).get('shop') || slug
    if (keep) p.set('shop', keep)
    for (const [k, v] of Object.entries(result.book_with || {})) if (v) p.set(k, v)
    nav(`/book?${p}`)
  }

  if (status && !status.available) {
    return (
      <section className="section" style={{ borderTop: 0 }}>
        <div className="wrap" style={{ maxWidth: 680 }}>
          <span className="eyebrow">Consultation</span>
          <h2 style={{ margin: '10px 0' }}>Not switched on yet</h2>
          <p className="muted">
            Photo consultations aren't available at {shop.name} right now. You can still
            choose your shape and colour on the booking form.
          </p>
        </div>
      </section>
    )
  }

  return (
    <section className="section" style={{ borderTop: 0 }}>
      <div className="wrap" style={{ maxWidth: 860 }}>
        <div className="section-head">
          <div>
            <span className="eyebrow">Consultation</span>
            <h2>Show us your hands</h2>
            <p>
              Send a photo and we'll tell you what we see and what we'd suggest — shape, length,
              finish and colour, all from our own menu. It goes straight into your booking.
            </p>
          </div>
        </div>

        <div className="grid two">
          <div className="card">
            <span className="bk-label">Your photo</span>
            <label className="cs-drop">
              {preview
                ? <img src={preview} alt="Your hands" />
                : <span className="muted">Tap to take or choose a photo of your hands</span>}
              <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment"
                     onChange={pick} hidden />
            </label>

            <label style={{ display: 'block', marginTop: 18 }}>
              <span className="bk-label">What are you after? (optional)</span>
              <textarea rows="3" value={note} onChange={(e) => setNote(e.target.value)}
                        className="cs-note"
                        placeholder="e.g. something short and neutral for work, but I want a bit of shine" />
            </label>

            {error && <p className="bk-error">{error}</p>}

            <button className="bk-submit" onClick={submit} disabled={!file || busy}>
              {busy ? 'Looking at your nails…' : 'Get my consultation'}
            </button>

            {busy && slow && (
              <p className="muted" style={{ fontSize: '0.84rem', marginTop: 12 }}>
                First consultation after a quiet spell takes a couple of minutes. Everything else
                on the site is instant if you'd rather not wait.
              </p>
            )}
          </div>

          <div>
            {!result && (
              <div className="card">
                <span className="eyebrow">What you'll get</span>
                <p className="muted" style={{ marginTop: 12, marginBottom: 0, fontSize: '0.9rem' }}>
                  A read on your nails as they are now, and shapes, finishes and shades chosen
                  from what {shop.name} actually offers — nothing we can't do.
                </p>
              </div>
            )}

            {result && (
              <div className="card">
                {result.asked_for && (
                  <p className="cs-asked">You asked for: “{result.asked_for}”</p>
                )}
                <span className="eyebrow">What we see</span>
                <div style={{ marginTop: 12 }}>
                  {Object.entries({
                    'Shape now': result.observed.nail_shape,
                    'Length': result.observed.length,
                    'On them now': result.observed.current_colour,
                    'Skin tone': result.observed.skin_tone,
                    'Condition': result.observed.condition,
                  }).filter(([, v]) => v).map(([k, v]) => (
                    <div key={k} className="bk-line"><span className="muted">{k}</span><span>{v}</span></div>
                  ))}
                </div>

                {result.consultation && (
                  <>
                    <hr className="rule" style={{ margin: '16px 0' }} />
                    <p style={{ marginBottom: 0 }}>{result.consultation}</p>
                  </>
                )}

                <hr className="rule" style={{ margin: '16px 0' }} />
                <span className="eyebrow">What we'd suggest</span>
                {result.why && <p className="muted" style={{ fontSize: '0.88rem', marginTop: 10 }}>{result.why}</p>}

                {['shapes', 'lengths', 'finishes'].map((k) => (
                  result.recommended[k]?.length > 0 && (
                    <div key={k} style={{ marginTop: 12 }}>
                      <span className="bk-label">{k}</span>
                      <div className="cs-chips">
                        {result.recommended[k].map((o) => (
                          <span key={o.id} className="cs-chip">
                            {o.label}{o.surcharge > 0 && <em> +{money(o.surcharge)}</em>}
                          </span>
                        ))}
                      </div>
                    </div>
                  )
                ))}

                {result.recommended.colours?.length > 0 && (
                  <div style={{ marginTop: 12 }}>
                    <span className="bk-label">Colours</span>
                    <div className="cs-chips">
                      {result.recommended.colours.map((c) => (
                        <span key={c.id} className="cs-chip">
                          <i className="cs-sw" style={{ background: c.hex }} />{c.name}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <button className="bk-submit" style={{ marginTop: 20 }} onClick={bookWithThese}>
                  Book with these
                </button>

                {/* The render step lives here from the start, switched off, so the
                    flow is whole and Phase 8 only flips it on. */}
                <div className={result.try_on?.available ? 'cs-tryon' : 'cs-tryon off'}>
                  <span className="bk-label">See it on your own hand</span>
                  <p className="muted" style={{ fontSize: '0.84rem', margin: '6px 0 0' }}>
                    {result.try_on?.available
                      ? 'Render the chosen look onto your photo.'
                      : result.try_on?.note || 'Coming soon.'}
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
