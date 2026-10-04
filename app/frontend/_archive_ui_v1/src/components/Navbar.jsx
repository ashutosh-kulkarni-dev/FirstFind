import { NavLink, useNavigate } from 'react-router-dom'
import { getUser, setAuth } from '../api'

export default function Navbar() {
  const user = getUser()
  const nav = useNavigate()
  return (
    <nav className="nav">
      <div className="nav-inner">
        <NavLink to="/" className="nav-logo">Thrift<em>Find</em></NavLink>
        <div className="nav-links">
          <NavLink to="/explore">Explore</NavLink>
          <NavLink to="/chat">Assistant</NavLink>
          <NavLink to="/zones">Zones</NavLink>
        </div>
        <div className="nav-user">
          {user ? (
            <>
              <span>Hi, {user.name.split(' ')[0]}</span>
              <button className="btn btn-sm" onClick={() => { setAuth(null, null); nav('/'); }}>
                Log out
              </button>
            </>
          ) : (
            <NavLink to="/auth" className="btn btn-sm btn-primary">Log in</NavLink>
          )}
        </div>
      </div>
    </nav>
  )
}
