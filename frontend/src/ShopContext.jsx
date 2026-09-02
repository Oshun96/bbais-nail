import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { applyTheme, setDocumentMeta } from './theme'
import { apiGet } from './api'

const ShopCtx = createContext(null)

/**
 * Which shop this page is. In production one deployment serves one shop and the
 * backend's DEFAULT_SHOP_SLUG decides; `?shop=` exists so a single preview can
 * demonstrate the white-label swap without a redeploy.
 */
function requestedSlug() {
  return new URLSearchParams(window.location.search).get('shop') || ''
}

export function ShopProvider({ children }) {
  const [shop, setShop] = useState(null)
  const [roster, setRoster] = useState([])
  const [error, setError] = useState(null)
  const [slug, setSlug] = useState(requestedSlug)

  useEffect(() => {
    let live = true
    setError(null)
    ;(async () => {
      try {
        const idx = await apiGet('/api/shops')
        if (!live) return
        setRoster(idx.shops || [])
        const target = slug || idx.default
        const cfg = await apiGet(`/api/shops/${encodeURIComponent(target)}/config`)
        if (!live) return
        applyTheme(cfg.theme)
        setDocumentMeta(cfg)
        setShop(cfg)
      } catch (e) {
        if (live) setError(e.message)
      }
    })()
    return () => {
      live = false
    }
  }, [slug])

  /**
   * Re-read the config in place after an admin edit.
   *
   * Deliberately does NOT clear `shop` first: blanking it unmounts the whole
   * tree (App renders a loading state), which would throw the admin back to its
   * first tab and discard whatever they were in the middle of.
   */
  const refreshShop = async () => {
    const target = slug || (await apiGet('/api/shops')).default
    const cfg = await apiGet(`/api/shops/${encodeURIComponent(target)}/config`)
    applyTheme(cfg.theme)
    setDocumentMeta(cfg)
    setShop(cfg)
    return cfg
  }

  const switchShop = (next) => {
    const url = new URL(window.location.href)
    if (next) url.searchParams.set('shop', next)
    else url.searchParams.delete('shop')
    window.history.replaceState({}, '', url)
    setShop(null)
    setSlug(next)
  }

  const value = useMemo(() => ({ shop, roster, error, slug, switchShop, refreshShop }),
    // refreshShop closes over `slug` only, so it does not need its own dep
    [shop, roster, error, slug])
  return <ShopCtx.Provider value={value}>{children}</ShopCtx.Provider>
}

export function useShop() {
  const ctx = useContext(ShopCtx)
  if (!ctx) throw new Error('useShop must be used inside <ShopProvider>')
  return ctx
}

/** Money in the shop's own currency — never a hardcoded dollar sign. */
export function useMoney() {
  const { shop } = useShop()
  const cur = shop?.payments?.currency || 'USD'
  return (n) =>
    new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: cur,
      minimumFractionDigits: Number.isInteger(n) ? 0 : 2,
    }).format(n || 0)
}

/** "09:00" -> "9:00 AM", using the viewer's locale conventions. */
export function fmtTime(hhmm) {
  const [h, m] = String(hhmm || '').split(':').map(Number)
  if (Number.isNaN(h)) return hhmm
  const d = new Date(2000, 0, 1, h, m || 0)
  return d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

export function fmtDuration(mins) {
  const h = Math.floor(mins / 60)
  const m = mins % 60
  if (!h) return `${m} min`
  return m ? `${h} hr ${m} min` : `${h} hr`
}
