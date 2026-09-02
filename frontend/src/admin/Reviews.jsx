import { useCallback, useEffect, useState } from 'react'
import { useShop } from '../ShopContext'
import { admin } from './adminApi'

/** Reviews left against real completed visits. The shop decides what shows. */
export default function Reviews({ onError }) {
  const { shop } = useShop()
  const [data, setData] = useState(null)

  const load = useCallback(async () => {
    try { setData(await admin(`/api/shops/${shop.slug}/admin/reviews`)) }
    catch (e) { onError(e) }
  }, [shop.slug, onError])

  useEffect(() => { load() }, [load])

  async function toggle(reference, published) {
    try {
      await admin(`/api/shops/${shop.slug}/admin/reviews/${reference}/publish`,
                  { method: 'POST', body: { published } })
      load()
    } catch (e) { onError(e) }
  }

  if (!data) return <p className="muted">Loading…</p>
  if (!data.reviews.length) return <p className="muted">No reviews yet.</p>

  return (
    <div>
      <p className="muted">
        {data.stats.count} published · average {data.stats.average} out of 5
      </p>
      {data.reviews.map((r) => (
        <div key={r.reference} className="card" style={{ marginBottom: 12 }}>
          <div className="bk-line">
            <strong>{'★'.repeat(r.rating)}{'☆'.repeat(5 - r.rating)} {r.client_name}</strong>
            <span className="muted">{r.visited_on}</span>
          </div>
          <p style={{ margin: '8px 0' }}>{r.text || <span className="muted">No comment left.</span>}</p>
          <div className="bk-line muted">
            <span>{r.service} · {r.technician_name}</span>
            <button className="ad-primary" onClick={() => toggle(r.reference, !r.published)}>
              {r.published ? 'Hide from the site' : 'Publish'}
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
