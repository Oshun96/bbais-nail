import { apiUrl } from '../api'

/**
 * Admin API access.
 *
 * The key lives in sessionStorage, not localStorage: it dies with the tab, so a
 * shared front-desk machine does not stay logged in after the browser closes.
 * It is only ever sent as a header to this platform's own API.
 */
const KEY = 'bbais-nail-admin-key'

export const getKey = () => sessionStorage.getItem(KEY) || ''
export const setKey = (k) => sessionStorage.setItem(KEY, k)
export const clearKey = () => sessionStorage.removeItem(KEY)

export class Unauthorized extends Error {}

export async function admin(path, { method = 'GET', body } = {}) {
  const res = await fetch(apiUrl(path), {
    method,
    headers: { 'Content-Type': 'application/json', 'X-Admin-Key': getKey() },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (res.status === 401) throw new Unauthorized('That key was not accepted.')
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail ? JSON.stringify(data.detail) : `Request failed (${res.status})`)
  return data
}
