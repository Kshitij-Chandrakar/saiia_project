import { useEffect, useRef } from 'react'
import mascot from '../assets/website-login/mascot.png'
import './website-recovery.css'
import { ProgressIndicator } from './WebsiteProgress'

// Plain anchors and local artwork keep this usable outside router/auth providers.
export default function WebsiteRecovery({ title, message, children, busy = false, contained = false, note, progress = false, focusOnChange = true }) {
  const heading = useRef(null)
  const focused = useRef(false)
  const Container = contained ? 'section' : 'main'
  const Heading = contained ? 'h2' : 'h1'
  useEffect(() => { if (!focused.current || focusOnChange) heading.current?.focus({ preventScroll: true }); focused.current = true }, [title, focusOnChange])
  return <Container className={`website-recovery${contained ? ' website-recovery--contained' : ''}`}>
    {!contained && <a className="wr-brand" href="/"><img src={mascot} alt="" width="48" height="40" onError={event => { event.currentTarget.hidden = true }} /><span>Intervucopilot</span></a>}
    <section className="wr-content" aria-labelledby="wr-title">
      <img className="wr-mascot" src={mascot} alt="" width="184" height="148" onError={event => { event.currentTarget.hidden = true }} />
      <div className="wr-copy">
        {progress && <ProgressIndicator />}
        <Heading id="wr-title" tabIndex={-1} ref={heading}>{title}</Heading>
        <p role="status" aria-live="polite" aria-atomic="true">{message}</p>
        <div className="wr-actions" aria-busy={busy}>{children}</div>
        {note && <p className="wr-note">{note}</p>}
      </div>
    </section>
    {!contained && <footer>Intervucopilot · Your interview workspace</footer>}
  </Container>
}
