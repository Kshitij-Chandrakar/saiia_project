import { useEffect, useRef } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import WebsiteRecovery from './auth/WebsiteRecovery'
import { websiteTitle } from './websiteMetadata'

const websitePaths = new Set(['/', '/landing', '/auth/login', '/auth/signup', '/auth/forgot-password', '/auth/status', '/auth/dashboard', '/auth/resume'])
let returnRoute = null

// Capture the previous known website path before the not-found screen renders.
// Go back uses navigate(-1) to avoid duplicating that history entry; never retain tokens.
export function WebsiteRouteHistory() {
  const location = useLocation()
  const previous = useRef(null)
  useEffect(() => {
    if (!window.electronAPI && !location.pathname.toLowerCase().startsWith('/auth/admin/')) {
      document.title = websiteTitle(location.pathname)
      let icon = document.querySelector('link[rel="icon"]')
      if (!icon) { icon = document.createElement('link'); icon.rel = 'icon'; document.head.append(icon) }
      icon.type = 'image/png'
      icon.setAttribute('href', '/website-favicon.png')
    } else if (!window.electronAPI) {
      const icon = document.querySelector('link[rel="icon"]')
      if (icon?.getAttribute('href') === '/website-favicon.png') {
        document.title = 'Vite + React'
        icon.type = 'image/svg+xml'
        icon.setAttribute('href', '/vite.svg')
      }
    }
    if (previous.current && previous.current.key !== location.key) {
      returnRoute = websitePaths.has(previous.current.pathname)
        ? { key: location.key, path: previous.current.pathname } : null
    }
    previous.current = { key: location.key, pathname: location.pathname }
  }, [location])
  return null
}

export default function WebsiteNotFound() {
  const location = useLocation()
  const navigate = useNavigate()
  useEffect(() => { document.title = 'Page not found | Intervucopilot' }, [location.key])
  return <WebsiteRecovery title="Page not found" message="We couldn’t find this page. Return to the homepage, or go back to where you were.">
    <Link to="/">Return home</Link>
    <button type="button" onClick={() => {
      if (returnRoute?.key === location.key) navigate(-1)
      else navigate('/', { replace: true })
    }}>Go back</button>
  </WebsiteRecovery>
}
