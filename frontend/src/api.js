/**
 * Where the API lives.
 *
 * Default is same-origin (""), which covers both the Vite dev proxy and a
 * production host that rewrites /api/* to the API service. If a deployment
 * cannot rewrite, set VITE_API_BASE to the API's origin at build time — the
 * value is never hardcoded here (0-hardcode rule).
 */
const BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '')

export function apiUrl(path) {
  return `${BASE}${path.startsWith('/') ? path : `/${path}`}`
}

export async function apiGet(path) {
  const res = await fetch(apiUrl(path))
  if (!res.ok) {
    const err = new Error(`${path} failed (${res.status})`)
    err.status = res.status
    throw err
  }
  return res.json()
}
