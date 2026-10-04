import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import Navbar from './components/Navbar'
import ChatWidget from './components/ChatWidget'
import Landing from './pages/Landing'
import Explore from './pages/Explore'
import Chat from './pages/Chat'
import StoreDetail from './pages/StoreDetail'
import Auth from './pages/Auth'
import Lists from './pages/Lists'
import NotFound from './pages/NotFound'

// Explore + Zones were merged into one map page at /explore. Keep /zones working
// (deep-links from chat/Lists carry ?lat&lng&radius) by redirecting, query intact.
function ZonesRedirect() {
  const { search } = useLocation()
  return <Navigate to={`/explore${search}`} replace />
}

export default function App() {
  const { pathname } = useLocation()
  // Landing carries its own hero nav; other pages use the shared dark navbar.
  const hideNav = pathname === '/'
  const hideWidget = pathname === '/chat' || pathname === '/auth' || pathname === '/'
  return (
    <div className="app-shell">
      {!hideNav && <Navbar />}
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/explore" element={<Explore />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/store/:id" element={<StoreDetail />} />
        <Route path="/zones" element={<ZonesRedirect />} />
        <Route path="/auth" element={<Auth />} />
        <Route path="/lists" element={<Lists />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
      {!hideWidget && <ChatWidget />}
    </div>
  )
}
