import { useShop, fmtTime } from '../ShopContext'

export default function Footer() {
  const { shop, slug } = useShop()
  // Keep the ?shop= selection when stepping into a staff screen.
  const staffHref = (p) => (slug ? `${p}?shop=${encodeURIComponent(slug)}` : p)
  const { derived } = shop
  const today = derived.day_order[(new Date().getDay() + 6) % 7] // JS weeks start Sunday

  return (
    <footer className="site-footer">
      <div className="wrap">
        <div className="foot-grid">
          <div>
            <h4>{shop.name}</h4>
            <p>{shop.tagline}</p>
          </div>

          <div>
            <h4>Find Us</h4>
            {shop.address.line1 && <p>{derived.address_one_line}</p>}
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
          </div>

          <div>
            <h4>Today</h4>
            <p>
              {shop.hours[today]?.closed
                ? 'Closed today'
                : `${fmtTime(shop.hours[today]?.open)} – ${fmtTime(shop.hours[today]?.close)}`}
            </p>
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

          <div>
            <h4>Deposits</h4>
            <p>{shop.deposit.policy_text || 'Ask the front desk about deposits.'}</p>
          </div>
        </div>

        <div className="colophon">
          <span>
            © {new Date().getFullYear()} {shop.name}
          </span>
          <span className="foot-staff">
            {/* Staff screens are reachable but deliberately understated — they
                are behind a key, not behind obscurity. */}
            <a href={staffHref('/desk')}>Front desk</a>
            <a href={staffHref('/admin')}>Admin</a>
            <span>Powered by BBAIS</span>
          </span>
        </div>
      </div>
    </footer>
  )
}
