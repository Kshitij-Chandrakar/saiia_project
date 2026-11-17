import './website-progress.css'

export function ProgressIndicator() {
  return <span className="website-progress-spinner" aria-hidden="true" />
}

export default function WebsiteProgress({ title, message, children, pending = true }) {
  return <section className="website-progress-notice" aria-label={title}>
    <div>{pending && <ProgressIndicator />}<h2>{title}</h2></div>
    <p role="status" aria-live="polite" aria-atomic="true">{message}</p>
    <div className="website-progress-actions">{children}</div>
  </section>
}
