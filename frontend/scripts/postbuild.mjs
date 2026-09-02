/**
 * Give every client-side route a real file on the static host.
 *
 * Render static sites have no SPA rewrite unless one is configured by hand, so
 * a direct hit on /services would 404 even though the app knows the route. This
 * writes dist/<route>/index.html for each route, which the host serves as a
 * directory index — clean URLs, no dashboard configuration, nothing to forget
 * when a page is added (the route list is shared with the router).
 */
import { copyFileSync, mkdirSync, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { SUBROUTES } from '../src/routes.js'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const dist = join(root, 'dist')
const index = join(dist, 'index.html')

if (!existsSync(index)) {
  console.error('postbuild: dist/index.html is missing — did vite build run?')
  process.exit(1)
}

for (const route of SUBROUTES) {
  const dir = join(dist, route)
  mkdirSync(dir, { recursive: true })
  copyFileSync(index, join(dir, 'index.html'))
  console.log(`postbuild: ${route}/index.html`)
}

// A catch-all for anything not in the list; the app redirects unknown paths home.
copyFileSync(index, join(dist, '404.html'))
console.log(`postbuild: 404.html`)

// ---------------------------------------------------------------- SEO files ---
// robots.txt and sitemap.xml must live at the SITE root to be honoured, so they
// cannot be proxied from the API. They are generated here from the same shop
// config the API reads, and the API also serves live copies for anything that
// needs to be current the moment a shop edits itself.
import { readFileSync, writeFileSync, readdirSync } from 'node:fs'

const SHOPS_DIR = join(root, '..', 'backend', 'shops')
const slug =
  process.env.VITE_SHOP_SLUG ||
  readdirSync(SHOPS_DIR).filter((f) => f.endsWith('.json')).sort()[0].replace('.json', '')
const shop = JSON.parse(readFileSync(join(SHOPS_DIR, `${slug}.json`), 'utf8'))
const SITE = (process.env.VITE_SITE_URL || 'https://bbais-nail.onrender.com').replace(/\/$/, '')
const API = (process.env.VITE_API_BASE || '').replace(/\/$/, '')

const DAYS = { mon: 'Monday', tue: 'Tuesday', wed: 'Wednesday', thu: 'Thursday',
               fri: 'Friday', sat: 'Saturday', sun: 'Sunday' }
const PAGES = [['/', '1.0', 'weekly'], ['/services', '0.9', 'weekly'], ['/menu', '0.8', 'monthly'],
               ['/team', '0.7', 'monthly'], ['/visit', '0.7', 'monthly'], ['/book', '0.9', 'weekly'],
               ['/consult', '0.6', 'monthly'], ['/chat', '0.5', 'monthly'], ['/check-in', '0.4', 'monthly']]

const ALLOW = ['GPTBot', 'OAI-SearchBot', 'ChatGPT-User', 'PerplexityBot', 'ClaudeBot',
               'Claude-User', 'Claude-SearchBot', 'Google-Extended', 'Applebot',
               'Applebot-Extended', 'Bingbot', 'DuckDuckBot']
const BLOCK = ['CCBot', 'Bytespider', 'Amazonbot', 'FacebookBot', 'Meta-ExternalAgent',
               'Omgilibot', 'Diffbot', 'Scrapy', 'magpie-crawler', 'DataForSeoBot']

writeFileSync(join(dist, 'robots.txt'),
  ['# Assistants answering questions about this shop are welcome.',
   '# Bulk scrapers are not.', '',
   ...ALLOW.flatMap((ua) => [`User-agent: ${ua}`, 'Allow: /', '']),
   ...BLOCK.flatMap((ua) => [`User-agent: ${ua}`, 'Disallow: /', '']),
   'User-agent: *', 'Allow: /', 'Disallow: /admin', 'Disallow: /desk', 'Disallow: /api/', '',
   `Sitemap: ${SITE}/sitemap.xml`, `# llms.txt: ${SITE}/llms.txt`].join('\n'))

writeFileSync(join(dist, 'sitemap.xml'),
  '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
  PAGES.map(([p, pri, freq]) =>
    `  <url><loc>${SITE}${p}</loc><changefreq>${freq}</changefreq><priority>${pri}</priority></url>`
  ).join('\n') + '\n</urlset>\n')

const active = (a) => (a || []).filter((x) => x.active !== false)
const money = shop.payments?.currency || 'USD'
writeFileSync(join(dist, 'llms.txt'), `# ${shop.name}

> ${shop.tagline || shop.seo?.description || ''}

${shop.about || ''}

## Contact
- Address: ${[shop.address?.line1, shop.address?.line2, shop.address?.city, shop.address?.state, shop.address?.postal_code].filter(Boolean).join(', ')}
- Phone: ${shop.contact?.phone || ''}
- Email: ${shop.contact?.email || ''}
- Book online: ${SITE}/book

## Hours
${Object.entries(DAYS).map(([k, label]) => {
  const h = shop.hours?.[k]
  return `- ${label}: ${!h || h.closed ? 'Closed' : `${h.open}–${h.close}`}`
}).join('\n')}

## Services
${active(shop.services).filter((s) => !s.addon).map((s) =>
  `- ${s.name} (${s.category}) — ${Math.round(s.price)} ${money}, ${s.duration_min} min in the chair` +
  (s.buffer_min ? `, ${s.buffer_min} min processing held` : '')).join('\n')}

## Nail menu
- Shapes: ${active(shop.nail_menu?.shapes).map((o) => o.label).join(', ')}
- Lengths: ${active(shop.nail_menu?.lengths).map((o) => o.label).join(', ')}
- Finishes: ${active(shop.nail_menu?.finishes).map((o) => o.label).join(', ')}

## Technicians
${active(shop.technicians).map((t) => `- ${t.name}, ${t.title} — ${(t.specialties || []).join(', ') || 'all services'}`).join('\n')}

## Booking
- Book at ${SITE}/book — real availability, deposits handled at the shop.
- Appointment times already include processing time, so a booked slot is the
  full chair time, not just the hands-on part.
- Deposits: ${shop.deposit?.policy_text || 'no deposit required'}

## Notes for assistants
- Prices and hours here come from this shop's configuration at build time.
- The always-current copy is at ${API || SITE}/api/shops/${slug}/llms.txt
- Do not quote a price or an opening time that is not on this page.
- To check real availability, send the person to ${SITE}/book rather than guessing.
`)

console.log(`postbuild: robots.txt, sitemap.xml, llms.txt for ${slug}`)
