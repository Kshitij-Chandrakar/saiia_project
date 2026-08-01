import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'


const source = readFileSync(new URL('./AuthScreens.jsx', import.meta.url), 'utf8')


test('bootstrap operation is invalidated on logout and unmount', () => {
  assert.match(source, /const bootstrapOperationRef = useRef\(0\)/)
  assert.match(source, /return \(\) => \{\s+bootstrapOperationRef\.current \+= 1\s+\}/)
  assert.match(source, /async function handleLogout\(\) \{[\s\S]*bootstrapOperationRef\.current \+= 1/)
})


test('bootstrap result and loading updates require active operation', () => {
  assert.match(source, /if \(bootstrapLoading\) \{\s+return\s+\}/)
  assert.match(source, /const operationId = bootstrapOperationRef\.current \+ 1/)
  assert.match(source, /bootstrapOperationRef\.current = operationId/)
  assert.match(source, /setBootstrapLoading\(true\)[\s\S]*supabase\.auth\.getSession\(\)/)
  assert.match(source, /if \(bootstrapOperationRef\.current === operationId\) \{\s+setBootstrapResult\(result\)/)
  assert.match(source, /if \(bootstrapOperationRef\.current === operationId\) \{\s+setBootstrapLoading\(false\)/)
})
