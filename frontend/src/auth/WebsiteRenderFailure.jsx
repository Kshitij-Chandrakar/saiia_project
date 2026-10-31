import WebsiteRecovery from './WebsiteRecovery'
import { useLayoutEffect } from 'react'

export function WebsiteMounted({ children }) {
  useLayoutEffect(() => {
    window.dispatchEvent(new Event('intervucopilot:mounted'))
  }, [])
  return children
}

export default function WebsiteRenderFailure() {
  useLayoutEffect(() => { document.title = 'Page unavailable | Intervucopilot' }, [])
  return <WebsiteRecovery title="This page couldn’t open" message="Something went wrong while opening this page. Reload it, or return home and choose where to go next." note={window.location.pathname === '/auth/checkout' ? 'If you were completing a payment, check its status before trying to pay again.' : undefined}>
    <a href="/">Return home</a><button type="button" onClick={() => window.location.reload()}>Reload page</button>
  </WebsiteRecovery>
}
