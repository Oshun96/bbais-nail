import { useState } from 'react'
import { useShop } from '../ShopContext'

/**
 * White-label proof surface: swaps the whole platform between shop configs.
 *
 * A single-shop deployment serves one config and never shows this — it only
 * appears when the API reports more than one shop available.
 */
export default function ShopSwitcher() {
  const { shop, roster, switchShop } = useShop()
  const [open, setOpen] = useState(false)

  if (!roster || roster.length < 2) return null

  return (
    <div className="switcher">
      {open ? (
        <div className="panel">
          <div className="lbl">Shop config</div>
          {roster.map((s) => (
            <button
              key={s.slug}
              className={s.slug === shop.slug ? 'on' : undefined}
              onClick={() => {
                switchShop(s.slug)
                setOpen(false)
              }}
            >
              <span className="dot" style={{ background: s.accent }} />
              {s.name}
            </button>
          ))}
          <button onClick={() => setOpen(false)} style={{ color: 'var(--muted)' }}>
            Close
          </button>
        </div>
      ) : (
        <div className="panel">
          <button onClick={() => setOpen(true)}>
            <span className="dot" style={{ background: shop.theme.accent || shop.theme.gold }} />
            {shop.name}
          </button>
        </div>
      )}
    </div>
  )
}
