import { test, expect } from '@playwright/test'
import { mkdir } from 'node:fs/promises'

test('downgrade preserves files and selects the permitted active set at desktop and narrow widths', async ({ page }) => {
  let selected = [], writes = []
  await page.route('**/src/main.jsx*', route => route.fulfill({ contentType: 'application/javascript', body: "import '/tests/catalog/fixtures/resume-access.jsx'" }))
  await page.route('**/src/auth/supabaseClient*', route => route.fulfill({ contentType: 'application/javascript', body: "export const supabase={auth:{getSession:async()=>({data:{session:{user:{id:'synthetic'},access_token:'fixture-only'}}})}}" }))
  await page.route('**/api/account/subscription', route => route.fulfill({ json: { usage: [{ meter: 'resume.stored_files', mode: 'limited', used: '2', allowance: '1' }] } }))
  await page.route('**/api/resumes', route => route.fulfill({ json: { items: ['one', 'two'].map(id => ({ id, status: 'ready', original_filename: `${id}.txt`, can_generate: selected.includes(id) })) } }))
  await page.route('**/api/resumes/active-set', route => {
    writes.push(route.request().postDataJSON())
    selected = writes.at(-1).resume_ids
    return route.fulfill({ json: { id: selected[0], status: 'ready' } })
  })
  await page.setViewportSize({ width: 1366, height: 768 })
  await page.goto('/')
  await expect(page.getByText('Your saved resumes are kept.', { exact: false })).toBeVisible()
  await page.getByRole('checkbox', { name: 'one.txt' }).check()
  await page.getByRole('checkbox', { name: 'two.txt' }).check()
  await expect(page.getByRole('button', { name: 'Use selected resumes' })).toBeDisabled()
  await page.getByRole('checkbox', { name: 'two.txt' }).uncheck()
  await page.getByRole('button', { name: 'Use selected resumes' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('status')).toHaveText('Resume access updated.')
  expect(writes).toEqual([{ resume_ids: ['one'] }])
  await expect(page.getByRole('checkbox', { name: 'one.txt' })).toBeChecked()
  await expect(page.getByRole('checkbox', { name: 'two.txt' })).toBeVisible()
  await mkdir('../docs/assets/subscriptions', { recursive: true })
  await page.screenshot({ path: '../docs/assets/subscriptions/c132-resume-access-desktop.png' })
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  await page.screenshot({ path: '../docs/assets/subscriptions/c132-resume-access-mobile.png' })
  await page.evaluate(() => window.switchResumeAccount())
  await expect(page.getByRole('checkbox')).toHaveCount(0)
})
