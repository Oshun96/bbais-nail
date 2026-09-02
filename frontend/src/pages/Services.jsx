import { useShop, useMoney, fmtDuration } from '../ShopContext'

export default function Services() {
  const { shop } = useShop()
  const money = useMoney()
  const active = shop.services.filter((s) => s.active)

  return (
    <section className="section" style={{ borderTop: 0 }}>
      <div className="wrap">
        <div className="section-head">
          <div>
            <span className="eyebrow">Service Menu</span>
            <h2>Everything on the book</h2>
            <p>
              Times shown are chair time. Where a service needs processing or dry time, it is already held on the
              calendar — that is why a fill is shorter than a full set.
            </p>
          </div>
        </div>

        {shop.derived.categories.map((cat) => (
          <div key={cat}>
            <h3 className="cat-title">{cat}</h3>
            {active
              .filter((s) => s.category === cat)
              .map((s) => (
                <div key={s.id} className="svc">
                  <div className="body">
                    <div className="name">
                      {s.name}
                      {s.is_fill && <span className="tag">Fill</span>}
                    </div>
                    {s.description && <div className="desc">{s.description}</div>}
                    <div className="meta">
                      {fmtDuration(s.duration_min)} in the chair
                      {s.buffer_min > 0 && ` · ${s.buffer_min} min processing held`}
                      {s.buffer_min > 0 && ` · ${fmtDuration(shop.derived.service_block_min[s.id])} booked`}
                    </div>
                  </div>
                  <div className="price">{money(s.price)}</div>
                </div>
              ))}
          </div>
        ))}

        <div className="card raised" style={{ marginTop: 44 }}>
          <span className="eyebrow">Deposits</span>
          <p style={{ marginTop: 10, marginBottom: 0 }}>
            {shop.deposit.enabled
              ? shop.deposit.policy_text ||
                `A ${
                  shop.deposit.kind === 'percent' ? `${shop.deposit.amount}%` : money(shop.deposit.amount)
                } deposit holds appointments of ${shop.deposit.applies_over_min} minutes or longer.`
              : 'No deposit required to book.'}
          </p>
        </div>
      </div>
    </section>
  )
}
