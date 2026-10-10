import { useEffect, useRef } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import './website-not-found.css'

const websitePaths = new Set(['/', '/landing', '/auth/login', '/auth/signup', '/auth/forgot-password', '/auth/status', '/auth/dashboard', '/auth/resume'])
let returnRoute = null

// Capture the previous known website path before the not-found screen renders.
// Go back uses navigate(-1) to avoid duplicating that history entry; never retain tokens.
export function WebsiteRouteHistory() {
  const location = useLocation()
  const previous = useRef(null)
  useEffect(() => {
    if (previous.current && previous.current.key !== location.key) {
      returnRoute = websitePaths.has(previous.current.pathname)
        ? { key: location.key, path: previous.current.pathname } : null
    }
    previous.current = location
  }, [location])
  return null
}

export default function WebsiteNotFound() {
  const location = useLocation()
  const navigate = useNavigate()
  const heading = useRef(null)
  useEffect(() => {
    const title = document.title
    document.title = 'Page not found | Intervucopilot'
    heading.current?.focus({ preventScroll: true })
    return () => { document.title = title }
  }, [location.key])
  return <main className="not-found" aria-labelledby="website-not-found-title">
    <h1 id="website-not-found-title" tabIndex={-1} ref={heading}>Page not found</h1>
    <p>The page you requested does not exist.</p>
    <Link to="/">Return home</Link>
    <button type="button" onClick={() => {
      if (returnRoute?.key === location.key) navigate(-1)
      else navigate('/', { replace: true })
    }}>Go back</button>
  </main>
}
