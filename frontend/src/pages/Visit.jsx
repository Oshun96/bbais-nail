import { useShop, useMoney, fmtTime } from '../ShopContext'

export default function Visit() {
  const { shop } = useShop()
  const money = useMoney()
  const { day_order, day_labels, address_one_line } = shop.derived
  const today = day_order[(new Date().getDay() + 6) % 7]

  return (
    <section className="section" style={{ borderTop: 0 }}>
      <div className="wrap">
        <div className="section-head">
          <div>
            <span className="eyebrow">Visit</span>
            <h2>Hours &amp; where to find us</h2>
            {shop.contact.booking_note && <p>{shop.contact.booking_note}</p>}
          </div>
        </div>

        <div className="grid two">
          <div className="card">
            <span className="eyebrow">Opening Hours</span>
            <div style={{ marginTop: 14 }}>
              {day_order.map((d) => {
                const h = shop.hours[d]
                return (
                  <div key={d} className={h?.closed ? 'hours-row closed' : 'hours-row'}>
                    <span className="d" style={d === today ? { color: 'var(--accent)' } : undefined}>
                      {day_labels[d]}
                      {d === today ? ' · today' : ''}
                    </span>
                    <span>{h?.closed ? 'Closed' : `${fmtTime(h.open)} – ${fmtTime(h.close)}`}</span>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="card">
            <span className="eyebrow">Contact</span>
            <div style={{ marginTop: 14 }}>
              {address_one_line && <p>{address_one_line}</p>}
              {shop.contact.phone && (
                <p>
                  <a href={`tel:${shop.contact.phone.replace(/[^\d+]/g, '')}`}>{shop.contact.phone}</a>
                </p>
              )}
              {shop.contact.email && (
                <p>
                  <a href={`mailto:${shop.contact.email}`}>{shop.contact.email}</a>
                </p>
              )}
              {shop.contact.instagram && (
                <p>
                  <a
                    href={`https://instagram.com/${shop.contact.instagram.replace('@', '')}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {shop.contact.instagram}
                  </a>
                </p>
              )}
            </div>

            <hr className="rule" style={{ margin: '22px 0' }} />

            <span className="eyebrow">Deposits &amp; Cancellations</span>
            <p className="muted" style={{ marginTop: 12, marginBottom: 0, fontSize: '0.92rem' }}>
              {shop.deposit.enabled
                ? shop.deposit.policy_text ||
                  `A ${
                    shop.deposit.kind === 'percent' ? `${shop.deposit.amount}%` : money(shop.deposit.amount)
                  } deposit holds appointments of ${shop.deposit.applies_over_min} minutes or longer. Free to change up to ${
                    shop.deposit.refundable_until_hours
                  } hours ahead.`
                : 'No deposit is required to book.'}
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
