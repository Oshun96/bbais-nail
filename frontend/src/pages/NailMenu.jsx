import { useShop, useMoney, fmtDuration } from '../ShopContext'
import { inkOn } from '../theme'

function OptionList({ title, blurb, options, money }) {
  if (!options?.length) return null
  return (
    <div className="card">
      <span className="eyebrow">{title}</span>
      <p className="muted" style={{ fontSize: '0.88rem', margin: '10px 0 6px' }}>
        {blurb}
      </p>
      {options
        .filter((o) => o.active)
        .map((o) => (
          <div key={o.id} className="opt-row">
            <div>
              <div className="label">{o.label}</div>
              {o.description && <div className="desc">{o.description}</div>}
            </div>
            <div className={o.surcharge > 0 ? 'up' : 'up free'}>
              {o.surcharge > 0 ? `+${money(o.surcharge)}` : 'Included'}
              {o.extra_min > 0 && (
                <div className="muted" style={{ fontSize: '0.72rem', textAlign: 'right' }}>
                  +{fmtDuration(o.extra_min)}
                </div>
              )}
            </div>
          </div>
        ))}
    </div>
  )
}

export default function NailMenu() {
  const { shop } = useShop()
  const money = useMoney()
  const { shapes, lengths, finishes } = shop.nail_menu
  const colours = shop.colours.filter((c) => c.active)

  return (
    <section className="section" style={{ borderTop: 0 }}>
      <div className="wrap">
        <div className="section-head">
          <div>
            <span className="eyebrow">The Menu</span>
            <h2>Shape, length, finish, colour</h2>
            <p>
              Specialty shapes and added length cost more because they take longer to sculpt and wear harder. Both are
              priced here, so nothing is a surprise at the desk.
            </p>
          </div>
        </div>

        <div className="grid three">
          <OptionList title="Shapes" blurb="How the free edge is filed." options={shapes} money={money} />
          <OptionList title="Lengths" blurb="How far past the fingertip." options={lengths} money={money} />
          <OptionList title="Finishes" blurb="What goes over the colour." options={finishes} money={money} />
        </div>

        {shop.derived.colour_families.map((family) => (
          <div key={family}>
            <h3 className="cat-title">{family}</h3>
            <div className="swatches">
              {colours
                .filter((c) => c.family === family)
                .map((c) => (
                  <div key={c.id} className="swatch">
                    <div className="chip" style={{ background: c.hex, color: inkOn(c.hex) }}>
                      <span>{c.finish}</span>
                    </div>
                    <div className="nm">{c.name}</div>
                  </div>
                ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
