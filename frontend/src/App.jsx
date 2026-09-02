import { Routes, Route, Navigate } from 'react-router-dom'
import { useShop } from './ShopContext'
import Header from './components/Header'
import Footer from './components/Footer'
import ShopSwitcher from './components/ShopSwitcher'
import Home from './pages/Home'
import Services from './pages/Services'
import Team from './pages/Team'
import NailMenu from './pages/NailMenu'
import Visit from './pages/Visit'
import Book from './pages/Book'
import CheckIn from './pages/CheckIn'
import Desk from './pages/Desk'
import Admin from './pages/Admin'

export default function App() {
  const { shop, error } = useShop()

  if (error) {
    return (
      <div className="state">
        <p className="err">{error}</p>
        <p>Check that the API is running and the shop slug exists.</p>
      </div>
    )
  }
  if (!shop) return <div className="state">Loading…</div>

  return (
    <>
      <Header />
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/services" element={<Services />} />
          <Route path="/team" element={<Team />} />
          <Route path="/menu" element={<NailMenu />} />
          <Route path="/visit" element={<Visit />} />
          <Route path="/book" element={<Book />} />
          <Route path="/check-in" element={<CheckIn />} />
          <Route path="/desk" element={<Desk />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <Footer />
      <ShopSwitcher />
    </>
  )
}
