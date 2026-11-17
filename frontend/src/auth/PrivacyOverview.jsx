export default function PrivacyOverview() {
  return <section className="privacy-export privacy-center" aria-labelledby="privacy-overview-title">
    <div className="privacy-center-intro"><h2 id="privacy-overview-title">Your privacy choices</h2><p>Download your data, manage interview history, or delete your account.</p></div>
    <div className="privacy-choice-grid" role="list" aria-label="Privacy actions">
      <div role="listitem"><strong>Download</strong><span>Get a private copy of your approved data. It expires 24 hours after it is ready.</span></div>
      <div role="listitem"><strong>Interview history</strong><span>Remove one interview or all history while reusable profile resources stay.</span></div>
      <div role="listitem"><strong>Delete account</strong><span>Access is restricted immediately after final confirmation. There is no undo.</span></div>
    </div>
    <details className="privacy-details"><summary>What data do we store?</summary><p>Account details, resumes and extracted text, job contexts, interview history, answers, AI Notes, Ask AI, saved Screen results, settings and consent. Usage, payment references and delivery status support account security and billing.</p></details>
    <details className="privacy-details"><summary>What may remain after deletion?</summary><p>Minimized usage/recovery metadata has a 90-day clock and minimized security/audit metadata has a 180-day clock, measured from accepted account deletion. Financial records, processor copies and backups follow separate requirements.</p><p>The deleted email remains permanently suppressed from signup. Necessary billing records remain while cancellation is unresolved; deletion does not confirm that future charges have stopped.</p></details>
    <details className="privacy-details"><summary>Devices and providers</summary><p>Connected devices can clear controlled account state. An offline or unmanaged device cannot be physically wiped remotely, shared-device files and downloads are preserved, and downloaded export bytes cannot be recalled.</p><p>Configured identity, storage, AI, transcription, billing and email processors must still be verified before activation. No zero-retention or backup-erasure deadline is promised.</p></details>
    <p className="privacy-verification-note" role="status"><strong>Some controls are still being verified.</strong> Export and destructive privacy controls remain unavailable in the normal application. Already downloaded export bytes cannot be recalled.</p>
  </section>
}
