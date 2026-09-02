import { useEffect, useRef, useState } from 'react'

/**
 * One card widget, three processors.
 *
 * The server has already opened the payment for an amount it calculated itself;
 * this component only collects the card and reports back. It never sees a secret
 * key and never states an amount — the server re-confirms with the provider
 * before anything is marked paid.
 *
 * Each SDK is loaded on demand, and only for the processor the shop actually
 * uses, so a Stripe shop never ships PayPal's script.
 */

function loadScript(src, id, attrs = {}) {
  return new Promise((resolve, reject) => {
    const existing = document.getElementById(id)
    if (existing) {
      if (existing.dataset.loaded === '1') return resolve()
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', reject)
      return
    }
    const s = document.createElement('script')
    s.id = id
    s.src = src
    s.async = true
    for (const [k, v] of Object.entries(attrs)) s.setAttribute(k, v)
    s.onload = () => { s.dataset.loaded = '1'; resolve() }
    s.onerror = () => reject(new Error(`could not load the ${id} payment library`))
    document.head.appendChild(s)
  })
}

export default function CardPayment({ payment, processor, amount, currency, onPaid, onError }) {
  const mount = useRef(null)
  const [status, setStatus] = useState('loading')
  const [msg, setMsg] = useState('')

  useEffect(() => {
    let dead = false
    const fail = (e) => {
      if (dead) return
      setStatus('error')
      setMsg(String(e.message || e))
      onError?.(e)
    }

    async function boot() {
      const c = payment?.client || {}
      try {
        // ---------------------------------------------------------- stripe ---
        if (processor === 'stripe') {
          if (!c.publishable_key) throw new Error('this shop has no Stripe publishable key set')
          await loadScript('https://js.stripe.com/v3/', 'stripe-js')
          if (dead) return
          const stripe = window.Stripe(c.publishable_key)
          const elements = stripe.elements({
            clientSecret: c.client_secret,
            appearance: { theme: 'night', variables: { colorPrimary: '#D4AF37' } },
          })
          const el = elements.create('payment')
          el.mount(mount.current)
          setStatus('ready')
          mount.current.__submit = async () => {
            const { error } = await stripe.confirmPayment({ elements, redirect: 'if_required' })
            if (error) throw new Error(error.message)
            return { payment_reference: payment.reference, client_token: '' }
          }
          return
        }

        // ---------------------------------------------------------- paypal ---
        if (processor === 'paypal') {
          if (!c.client_id) throw new Error('this shop has no PayPal client id set')
          await loadScript(
            `https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(c.client_id)}&currency=${c.currency}&intent=capture`,
            'paypal-js'
          )
          if (dead) return
          window.paypal.Buttons({
            style: { color: 'gold', shape: 'rect', label: 'pay' },
            // The order already exists server-side for the server's amount.
            createOrder: () => c.order_id,
            onApprove: async () => onPaid({ payment_reference: payment.reference, client_token: '' }),
            onError: fail,
          }).render(mount.current)
          setStatus('ready')
          return
        }

        // ---------------------------------------------------------- square ---
        if (processor === 'square') {
          if (!c.application_id || !c.location_id) throw new Error('this shop has no Square application/location id set')
          await loadScript(
            payment.sandbox
              ? 'https://sandbox.web.squarecdn.com/v1/square.js'
              : 'https://web.squarecdn.com/v1/square.js',
            'square-js'
          )
          if (dead) return
          const sq = window.Square.payments(c.application_id, c.location_id)
          const card = await sq.card()
          await card.attach(mount.current)
          setStatus('ready')
          mount.current.__submit = async () => {
            const res = await card.tokenize()
            if (res.status !== 'OK') throw new Error(res.errors?.[0]?.message || 'that card could not be read')
            return { payment_reference: payment.reference, client_token: res.token }
          }
          return
        }

        throw new Error(`unsupported processor ${processor}`)
      } catch (e) {
        fail(e)
      }
    }

    boot()
    return () => { dead = true }
  }, [processor, payment])

  async function pay() {
    try {
      setStatus('paying')
      const out = await mount.current.__submit()
      await onPaid(out)
    } catch (e) {
      setStatus('ready')
      setMsg(String(e.message || e))
      onError?.(e)
    }
  }

  return (
    <div className="pay">
      {payment?.sandbox && <p className="pay-sandbox">Sandbox mode — no real money moves.</p>}
      <div ref={mount} className="pay-mount" />
      {status === 'loading' && <p className="muted">Loading the card form…</p>}
      {msg && <p className="bk-error">{msg}</p>}
      {/* PayPal renders its own button; the others need ours. */}
      {processor !== 'paypal' && status !== 'loading' && (
        <button className="bk-submit" onClick={pay} disabled={status === 'paying'}>
          {status === 'paying' ? 'Taking payment…' : `Pay ${new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(amount)}`}
        </button>
      )}
    </div>
  )
}
