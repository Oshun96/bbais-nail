import { useCallback, useEffect, useRef, useState } from 'react'
import { useShop } from '../ShopContext'
import { apiUrl, apiGet } from '../api'

/**
 * The front-desk conversation. Shared by the bubble and the full chat page, so
 * both are the same desk — same conversation, same abilities.
 *
 * Cold start is disclosed rather than engineered away: if a reply is slow, we
 * say so and point at the instant booking form. No keep-warm pinging.
 */

// Namespaced per shop: previews share one origin, so an un-namespaced key would
// leak one shop's conversation into another.
const cidKey = (slug) => `bbais-nail:${slug}:conversation`

export default function AgentChat({ compact = false, onAction }) {
  const { shop } = useShop()
  const [status, setStatus] = useState(null)
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [slow, setSlow] = useState(false)
  const [error, setError] = useState('')
  const endRef = useRef(null)
  const slowTimer = useRef(null)

  const cid = useCallback(() => {
    try { return localStorage.getItem(cidKey(shop.slug)) || '' } catch { return '' }
  }, [shop.slug])

  useEffect(() => {
    let live = true
    apiGet(`/api/shops/${shop.slug}/agent/status`)
      .then((s) => live && setStatus(s))
      .catch(() => live && setStatus({ available: false }))

    const id = cid()
    if (id) {
      apiGet(`/api/shops/${shop.slug}/agent/conversations/${id}`)
        .then((c) => live && setMessages(c.messages || []))
        .catch(() => {})
    }
    return () => { live = false }
  }, [shop.slug, cid])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, busy])

  async function send(e) {
    e?.preventDefault()
    const text = draft.trim()
    if (!text || busy) return

    setDraft('')
    setError('')
    setMessages((m) => [...m, { role: 'user', content: text }])
    setBusy(true)
    setSlow(false)
    // Only mention the wait once it IS a wait.
    slowTimer.current = setTimeout(() => setSlow(true), 8000)

    try {
      const res = await fetch(apiUrl(`/api/shops/${shop.slug}/agent/chat`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, conversation_id: cid() || undefined }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'The desk could not answer just now.')
      try { localStorage.setItem(cidKey(shop.slug), data.conversation_id) } catch { /* private mode */ }
      setMessages((m) => [...m, { role: 'assistant', content: data.reply }])
      if (data.actions?.length) onAction?.(data.actions)
    } catch (err) {
      setError(String(err.message || err))
    } finally {
      clearTimeout(slowTimer.current)
      setBusy(false)
      setSlow(false)
    }
  }

  function reset() {
    try { localStorage.removeItem(cidKey(shop.slug)) } catch { /* private mode */ }
    setMessages([])
    setError('')
  }

  if (status && !status.available) {
    return (
      <div className="ag-unavailable">
        <p className="muted">
          The front desk isn't connected yet. You can still book instantly with the booking form.
        </p>
      </div>
    )
  }

  return (
    <div className={compact ? 'ag ag-compact' : 'ag'}>
      <div className="ag-log">
        {messages.length === 0 && (
          <div className="ag-msg assistant">
            {status?.greeting || `Welcome to ${shop.name}. How can I help?`}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`ag-msg ${m.role}`}>{m.content}</div>
        ))}
        {busy && (
          <div className="ag-msg assistant ag-typing">
            <span className="ag-dots"><i /><i /><i /></span>
            {slow && (
              <span className="ag-slow">
                Just waking the desk up — this first reply can take a couple of minutes.
                The <a href="/book">booking form</a> is instant if you'd rather not wait.
              </span>
            )}
          </div>
        )}
        {error && <div className="ag-msg error">{error}</div>}
        <div ref={endRef} />
      </div>

      <form className="ag-input" onSubmit={send}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={`Ask ${shop.agent?.name || 'the front desk'}…`}
          disabled={busy}
          aria-label="Message the front desk"
        />
        <button disabled={!draft.trim() || busy}>Send</button>
      </form>

      {messages.length > 0 && (
        <button className="ag-reset" onClick={reset}>Start a new conversation</button>
      )}
    </div>
  )
}
