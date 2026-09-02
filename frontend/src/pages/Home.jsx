import { Link, useLocation } from 'react-router-dom'
import { useShop, useMoney, fmtTime } from '../ShopContext'
import { inkOn } from '../theme'

export default function Home() {
  const { shop } = useShop()
  const money = useMoney()
  const { derived } = shop
  const loc = useLocation()
  const keep = new URLSearchParams(loc.search).get('shop')
  const to = (p) => (keep ? `${p}?shop=${encodeURIComponent(keep)}` : p)

  const today = derived.day_order[(new Date().getDay() + 6) % 7]
  const todayHours = shop.hours[today]
  const featured = shop.services.filter((s) => s.active).slice(0, 6)
  const swatches = shop.colours.filter((c) => c.active).slice(0, 12)

  return (
    <>
      <section className="hero">
        <div className="wrap">
          <div className="inner">
          <span className="eyebrow">
            {shop.address.city}
            {shop.address.state ? ` · ${shop.address.state}` : ''}
          </span>
          <h1>{shop.tagline || shop.name}</h1>
          <p>{shop.about}</p>

          <div className="hero-facts">
            <div>
              <span className="k">Today</span>
              {todayHours?.closed ? 'Closed' : `${fmtTime(todayHours?.open)} – ${fmtTime(todayHours?.close)}`}
            </div>
            <div>
              <span className="k">Services from</span>
              {money(derived.price_from)}
            </div>
            <div>
              <span className="k">Technicians</span>
              {shop.technicians.filter((t) => t.active).length} on the floor
            </div>
            {shop.contact.phone && (
              <div>
                <span className="k">Call</span>
                <a href={`tel:${shop.contact.phone.replace(/[^\d+]/g, '')}`}>{shop.contact.phone}</a>
              </div>
            )}
            </div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="wrap">
          <div className="section-head">
            <div>
              <span className="eyebrow">The Work</span>
              <h2>What we do</h2>
              <p>Every appointment is booked with its processing time built in, so the chair is yours for as long as the set actually takes.</p>
            </div>
            <Link to={to('/services')} className="eyebrow">
              Full menu →
            </Link>
          </div>

          <div className="grid three">
            {featured.map((s) => (
              <article key={s.id} className="card">
                <h3>{s.name}</h3>
                <p className="muted" style={{ fontSize: '0.9rem', marginTop: 8 }}>
                  {s.description}
                </p>
                <p style={{ margin: 0, color: 'var(--accent)', fontFamily: 'var(--font-heading)', fontSize: '1.3rem' }}>
                  {money(s.price)}
                </p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="wrap">
          <div className="section-head">
            <div>
              <span className="eyebrow">The Colour Wall</span>
              <h2>{shop.colours.filter((c) => c.active).length} shades on the shelf</h2>
              <p>Across {derived.colour_families.join(', ').toLowerCase()}.</p>
            </div>
            <Link to={to('/menu')} className="eyebrow">
              Shapes, lengths & finishes →
            </Link>
          </div>

          <div className="swatches">
            {swatches.map((c) => (
              <div key={c.id} className="swatch">
                <div className="chip" style={{ background: c.hex, color: inkOn(c.hex) }}>
                  <span>{c.finish}</span>
                </div>
                <div className="nm">{c.name}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="wrap">
          <div className="section-head">
            <div>
              <span className="eyebrow">The Room</span>
              <h2>Who you'll sit with</h2>
            </div>
            <Link to={to('/team')} className="eyebrow">
              Meet everyone →
            </Link>
          </div>

          <div className="grid three">
            {shop.technicians
              .filter((t) => t.active)
              .slice(0, 3)
              .map((t) => (
                <article key={t.id} className="card">
                  <div className="tech-head">
                    <span className="tech-photo">
                      {t.photo_url ? <img src={t.photo_url} alt={t.name} /> : t.name.slice(0, 1)}
                    </span>
                    <span>
                      <h3 style={{ fontSize: '1.25rem' }}>{t.name}</h3>
                      <span className="muted" style={{ fontSize: '0.8rem' }}>
                        {t.title}
                      </span>
                    </span>
                  </div>
                  <p className="muted" style={{ fontSize: '0.9rem', marginTop: 14, marginBottom: 0 }}>
                    {t.bio}
                  </p>
                </article>
              ))}
          </div>
        </div>
      </section>
    </>
  )
}
