import { useShop, fmtTime } from '../ShopContext'

export default function Team() {
  const { shop } = useShop()
  const { day_order, day_labels } = shop.derived

  return (
    <section className="section" style={{ borderTop: 0 }}>
      <div className="wrap">
        <div className="section-head">
          <div>
            <span className="eyebrow">Our Team</span>
            <h2>Who you'll sit with</h2>
            <p>Book by name, or let the front desk match you to whoever does the work you're after.</p>
          </div>
        </div>

        <div className="grid two">
          {shop.technicians
            .filter((t) => t.active)
            .map((t) => (
              <article key={t.id} className="card">
                <div className="tech-head">
                  <span className="tech-photo">
                    {t.photo_url ? <img src={t.photo_url} alt={t.name} /> : t.name.slice(0, 1)}
                  </span>
                  <span>
                    <h3>{t.name}</h3>
                    <span className="muted" style={{ fontSize: '0.82rem' }}>
                      {t.title}
                    </span>
                  </span>
                </div>

                {t.bio && (
                  <p className="muted" style={{ fontSize: '0.92rem', marginTop: 16 }}>
                    {t.bio}
                  </p>
                )}

                {t.specialties?.length > 0 && (
                  <div className="spec">
                    {t.specialties.map((s) => (
                      <span key={s}>{s}</span>
                    ))}
                  </div>
                )}

                <div style={{ marginTop: 20 }}>
                  <span className="eyebrow" style={{ fontSize: '0.62rem' }}>
                    On the floor
                  </span>
                  <div style={{ marginTop: 8 }}>
                    {day_order.map((d) => {
                      const day = t.schedule?.[d]
                      const off = !day || day.off
                      return (
                        <div key={d} className={off ? 'hours-row closed' : 'hours-row'}>
                          <span className="d">{day_labels[d]}</span>
                          <span>{off ? '—' : `${fmtTime(day.start)} – ${fmtTime(day.end)}`}</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </article>
            ))}
        </div>
      </div>
    </section>
  )
}
