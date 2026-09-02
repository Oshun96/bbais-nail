/**
 * The shop config -> CSS custom properties.
 *
 * Every colour, font and brand mark in the UI reads a variable set here, so a
 * different shop config repaints the whole platform without a line of code
 * changing. `accent` is the shop's override; it falls back to BBAIS gold.
 */

const GOOGLE_FONT_HREF = (families) =>
  'https://fonts.googleapis.com/css2?' +
  families.map((f) => `family=${f.trim().replace(/ /g, '+')}:wght@300;400;500;600;700`).join('&') +
  '&display=swap'

export function applyTheme(theme) {
  if (!theme) return
  const r = document.documentElement.style
  const accent = theme.accent || theme.gold

  r.setProperty('--base', theme.base)
  r.setProperty('--surface', theme.surface)
  r.setProperty('--surface-raised', theme.surface_raised)
  r.setProperty('--line', theme.line)
  r.setProperty('--gold', theme.gold)
  r.setProperty('--rose-gold', theme.rose_gold)
  r.setProperty('--text', theme.text)
  r.setProperty('--muted', theme.muted)
  r.setProperty('--accent', accent)
  r.setProperty('--accent-soft', hexA(accent, 0.14))
  r.setProperty('--accent-line', hexA(accent, 0.34))
  r.setProperty('--font-heading', `"${theme.heading_font}", "Cormorant Garamond", Georgia, serif`)
  r.setProperty('--font-body', `"${theme.body_font}", "DM Sans", system-ui, sans-serif`)

  loadFonts([theme.heading_font, theme.body_font])
}

/** Swap the stylesheet only when the family set actually changes. */
let loadedKey = ''
function loadFonts(families) {
  const key = families.join('|')
  if (key === loadedKey) return
  loadedKey = key
  let link = document.getElementById('bbais-fonts')
  if (!link) {
    link = document.createElement('link')
    link.id = 'bbais-fonts'
    link.rel = 'stylesheet'
    document.head.appendChild(link)
  }
  link.href = GOOGLE_FONT_HREF(families)
}

/** #rrggbb -> rgba(), so one accent yields its own tints without extra config. */
export function hexA(hex, alpha) {
  let h = String(hex || '').replace('#', '')
  if (h.length === 3) h = h.split('').map((c) => c + c).join('')
  const n = parseInt(h || '000000', 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
}

/** Readable ink for a swatch — decides black vs white text per polish colour. */
export function inkOn(hex) {
  let h = String(hex || '').replace('#', '')
  if (h.length === 3) h = h.split('').map((c) => c + c).join('')
  const n = parseInt(h || '000000', 16)
  const l = 0.2126 * ((n >> 16) & 255) + 0.7152 * ((n >> 8) & 255) + 0.0722 * (n & 255)
  return l > 150 ? '#101010' : '#F5F1E8'
}

export function setDocumentMeta(shop) {
  if (!shop) return
  document.title = shop.seo?.title || `${shop.name}${shop.tagline ? ' — ' + shop.tagline : ''}`
  let m = document.querySelector('meta[name="description"]')
  if (!m) {
    m = document.createElement('meta')
    m.name = 'description'
    document.head.appendChild(m)
  }
  m.content = shop.seo?.description || shop.about || ''
  let tc = document.querySelector('meta[name="theme-color"]')
  if (!tc) {
    tc = document.createElement('meta')
    tc.name = 'theme-color'
    document.head.appendChild(tc)
  }
  tc.content = shop.theme?.base || '#000000'
}
