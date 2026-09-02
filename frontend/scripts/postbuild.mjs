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
