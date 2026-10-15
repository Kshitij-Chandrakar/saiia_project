export const GOOGLE_SIGNUP_CONSENT_KEY = 'intervuai.googleSignupAttempt'
export const GOOGLE_SIGNUP_CONSENT_TTL_MS = 10 * 60 * 1000

export function beginGoogleSignupConsent(consent) {
  const attempt = crypto.randomUUID()
  sessionStorage.setItem(GOOGLE_SIGNUP_CONSENT_KEY, JSON.stringify({ attempt, createdAt: Date.now(), consent }))
  return attempt
}

export function readGoogleSignupConsent(attempt) {
  try {
    const record = JSON.parse(sessionStorage.getItem(GOOGLE_SIGNUP_CONSENT_KEY) || 'null')
    if (!record) return null
    const age = Date.now() - record.createdAt
    const consent = record.consent
    if (!Number.isFinite(age) || age < 0 || age >= GOOGLE_SIGNUP_CONSENT_TTL_MS ||
        consent?.terms_accepted !== true || consent?.privacy_accepted !== true ||
        ![null, true, false].includes(consent.marketing_email_opt_in) ||
        consent.consent_source !== 'signup' || consent.consent_version !== 'c10.6a-v1') {
      sessionStorage.removeItem(GOOGLE_SIGNUP_CONSENT_KEY)
      return null
    }
    if (!attempt || record.attempt !== attempt) return null
    // Allowlisted preferences only: browser data never supplies account identity.
    return { consent: { terms_accepted: true, privacy_accepted: true,
      marketing_email_opt_in: consent.marketing_email_opt_in,
      consent_source: 'signup', consent_version: 'c10.6a-v1' } }
  } catch { return null }
}

export function clearGoogleSignupConsent(attempt) {
  try {
    const record = JSON.parse(sessionStorage.getItem(GOOGLE_SIGNUP_CONSENT_KEY) || 'null')
    if (record?.attempt === attempt) sessionStorage.removeItem(GOOGLE_SIGNUP_CONSENT_KEY)
  } catch { /* Storage unavailable: the expiry still prevents reuse. */ }
}
