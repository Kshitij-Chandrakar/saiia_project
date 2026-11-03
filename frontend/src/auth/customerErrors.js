// Classification is separate from presentation. Never echo arbitrary message/detail.
const authMessages = {
  invalid_credentials: 'Invalid email or password.',
  email_not_confirmed: 'Verify your email before signing in.',
  user_already_exists: 'An account may already exist. Try signing in or resetting your password.',
  weak_password: 'Choose a stronger password. Follow the requirements beside the password field.',
  email_address_invalid: 'Enter a valid email address.',
  over_request_rate_limit: 'Too many attempts. Please wait before trying again.',
  over_email_send_rate_limit: 'Please wait before requesting another email.',
}

export function customerError(error, fallback = 'We couldn’t complete that request. Please try again.') {
  if (error?.code && Object.hasOwn(authMessages, error.code)) return authMessages[error.code]
  if (error?.status === 429) return 'Too many attempts. Please wait before trying again.'
  if (error?.status === 401) return 'Please sign in again to continue.'
  if (error?.status === 403) return 'This action isn’t available for your account.'
  return fallback
}

export function customerWebsiteError(error, fallback) {
  return window.electronAPI ? error?.message || fallback : customerError(error, fallback)
}
