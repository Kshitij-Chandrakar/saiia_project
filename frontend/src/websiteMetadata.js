const titles = {
  '/': 'Intervucopilot', '/landing': 'Intervucopilot',
  '/auth/login': 'Sign in', '/auth/signup': 'Create account',
  '/auth/desktop-login': 'Desktop sign in', '/auth/forgot-password': 'Reset password',
  '/auth/reset-password': 'Choose a new password', '/auth/confirm': 'Verify your email',
  '/auth/callback': 'Signing you in', '/auth/status': 'Account',
  '/unsubscribe': 'Email preferences', '/auth/onboarding': 'Get started',
  '/auth/dashboard': 'Dashboard', '/auth/sessions': 'Sessions',
  '/auth/resume': 'Resumes', '/auth/checkout': 'Secure checkout', '/auth/logout': 'Sign out',
}

// Titles come only from route constants, never customer or URL payloads.
export function websiteTitle(pathname) {
  const route = pathname.replace(/\/+$/, '').toLowerCase() || '/'
  const title = titles[route] || 'Page not found'
  return title === 'Intervucopilot' ? title : `${title} | Intervucopilot`
}
