import { useShop } from '../ShopContext'
import AgentChat from '../components/AgentChat'

/** The full-page front desk — the same conversation as the bubble. */
export default function Chat() {
  const { shop } = useShop()
  return (
    <section className="section" style={{ borderTop: 0 }}>
      <div className="wrap" style={{ maxWidth: 780 }}>
        <div className="section-head">
          <div>
            <span className="eyebrow">{shop.agent?.name || 'Front Desk'}</span>
            <h2>Talk to us</h2>
            <p>
              Ask about anything on the menu, or just say what you want and when — we can book you
              in, check you in, or put you in today's line right here.
            </p>
          </div>
        </div>
        <AgentChat />
      </div>
    </section>
  )
}
