import { test } from 'node:test'
import assert from 'node:assert/strict'
import { websiteTitle } from './websiteMetadata.js'

test('customer titles use a fixed route vocabulary without URL payloads', () => {
  for (const [path, title] of [['/', 'Intervucopilot'], ['/auth/login', 'Sign in | Intervucopilot'], ['/auth/resume', 'Resumes | Intervucopilot'], ['/auth/checkout', 'Secure checkout | Intervucopilot'], ['/unsubscribe', 'Email preferences | Intervucopilot']]) assert.equal(websiteTitle(path), title)
  for (const path of ['/unknown/customer@example.test', '/auth/callback?token=secret', '/<script>private</script>', '/auth/resume/deleted-customer-record']) assert.equal(websiteTitle(path), 'Page not found | Intervucopilot')
  assert.equal(websiteTitle('/AUTH/LOGIN/'), 'Sign in | Intervucopilot')
})
