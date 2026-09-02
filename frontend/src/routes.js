/**
 * The site's routes, in nav order — the single source of truth.
 *
 * The router, the header nav and the post-build step all read this list, so a
 * new page can never be added to the nav without also getting a real file on
 * the static host (see scripts/postbuild.mjs).
 */
export const NAV = [
  { path: '/', label: 'Home' },
  { path: '/services', label: 'Services' },
  { path: '/menu', label: 'The Menu' },
  { path: '/team', label: 'Our Team' },
  { path: '/visit', label: 'Visit' },
  { path: '/book', label: 'Book' },
  { path: '/check-in', label: 'Check In' },
  { path: '/consult', label: 'Consultation' },
  { path: '/chat', label: 'Chat' },
]

/** Staff screens: real routes that need files on the host, but kept out of the
 *  client-facing nav. */
export const STAFF = ['/desk', '/admin']

/** Every route except "/", which the host already serves as index.html. */
export const SUBROUTES = [...NAV.map((r) => r.path), ...STAFF].filter((p) => p !== '/')
