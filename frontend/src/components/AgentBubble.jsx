import { useLocation } from 'react-router-dom'
import { useState } from 'react'
import { useShop } from '../ShopContext'
import AgentChat from './AgentChat'

/**
 * The front desk, on every page.
 *
 * Hidden on the full chat page (where it would duplicate itself) and on staff
 * screens, which have their own tools.
 */
const HIDE_ON = ['/chat', '/desk', '/admin']

export default function AgentBubble() {
  const { shop } = useShop()
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)

  if (HIDE_ON.some((p) => pathname.startsWith(p))) return null

  return (
    <>
      {open && (
        <div className="ag-panel">
          <div className="ag-head">
            <span>
              <strong>{shop.agent?.name || 'Front Desk'}</strong>
              <span className="muted"> · {shop.name}</span>
            </span>
            <button onClick={() => setOpen(false)} aria-label="Close chat">×</button>
          </div>
          <AgentChat compact />
        </div>
      )}
      <button className={`ag-bubble${open ? ' open' : ''}`} onClick={() => setOpen((v) => !v)}
              aria-label={open ? 'Close the front desk chat' : 'Chat with the front desk'}>
        {open ? '×' : 'Chat'}
      </button>
    </>
  )
}
