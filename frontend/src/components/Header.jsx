import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useShop } from '../ShopContext'
import { NAV } from '../routes'

export default function Header() {
  const { shop } = useShop()
  const [open, setOpen] = useState(false)
  const loc = useLocation()

  // `?shop=` must survive navigation or the demo swap resets on every click.
  const keep = new URLSearchParams(loc.search).get('shop')
  const to = (p) => (keep ? `${p}?shop=${encodeURIComponent(keep)}` : p)

  return (
    <header className="site-header">
      <div className="wrap bar">
        <NavLink to={to('/')} className="brand" onClick={() => setOpen(false)}>
          <span className="brand-mark">
            {shop.theme.logo_url ? (
              <img src={shop.theme.logo_url} alt={shop.name} />
            ) : (
              shop.theme.logo_mark || shop.name.slice(0, 2).toUpperCase()
            )}
          </span>
          <span>
            <span className="brand-name">{shop.name}</span>
            {shop.address.city && (
              <span className="brand-tag" style={{ display: 'block' }}>
                {shop.address.city}
                {shop.address.state ? `, ${shop.address.state}` : ''}
              </span>
            )}
          </span>
        </NavLink>

        <button
          className="nav-toggle"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-controls="site-nav"
        >
          {open ? 'Close' : 'Menu'}
        </button>

        {/* Visibility is CSS-driven so it tracks resizes; JS only holds intent. */}
        <nav className={open ? 'nav open' : 'nav'} id="site-nav">
          {NAV.map(({ path, label }) => (
            <NavLink
              key={path}
              to={to(path)}
              end={path === '/'}
              onClick={() => setOpen(false)}
              className={({ isActive }) => (isActive ? 'active' : undefined)}
            >
              {label}
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  )
}
