import { Routes, Route, useLocation } from 'react-router-dom'
import Navbar from './components/Navbar'
import ChatWidget from './components/ChatWidget'
import Landing from './pages/Landing'
import Explore from './pages/Explore'
import Chat from './pages/Chat'
import StoreDetail from './pages/StoreDetail'
import Zones from './pages/Zones'
import Auth from './pages/Auth'

export default function App() {
  const { pathname } = useLocation()
  const hideWidget = pathname === '/chat' || pathname === '/auth'
  return (
    <>
      <Navbar />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/explore" element={<Explore />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/store/:id" element={<StoreDetail />} />
        <Route path="/zones" element={<Zones />} />
        <Route path="/auth" element={<Auth />} />
      </Routes>
      {!hideWidget && <ChatWidget />}
    </>
  )
}
