import { test, expect, _electron as electron } from '@playwright/test'
import { mkdtemp, rm, mkdir, access, readFile, unlink, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { execFileSync } from 'node:child_process'

test.use({ trace: 'off' })
const configuration = process.env.CATALOG_BROWSER_NATIVE ? JSON.parse(process.env.CATALOG_BROWSER_NATIVE) : null
const native = configuration ? { ...configuration, ...configuration.electron } : null

test('actual Windows Electron main, preload, current plan, Upgrade and logout', async () => {
  test.skip(!native || process.platform !== 'win32', 'Disposable native Windows runner required')
  const directory = await mkdtemp(path.join(os.tmpdir(), 'c132-electron-'))
  const env = { ...process.env }
  delete env.ELECTRON_RUN_AS_NODE
  delete env.CATALOG_BROWSER_NATIVE
  const isolated = {
    ...env, C132_ELECTRON_DATA: directory,
    C132_ELECTRON_SESSION: JSON.stringify({ access_token: native.token, refresh_token: 'synthetic-only', expires_at: Math.floor(Date.now() / 1000) + 3600 }),
    SUPABASE_URL: native.url, VITE_SUPABASE_URL: native.url,
    SUPABASE_ANON_KEY: 'synthetic-public-key', VITE_SUPABASE_ANON_KEY: 'synthetic-public-key',
    SAIIA_BACKEND_URL: native.url, VITE_BACKEND_URL: native.url,
    SAIIA_WEB_AUTH_URL: 'http://127.0.0.1:5186/auth/desktop-login',
    SAIIA_WEB_DASHBOARD_URL: 'http://127.0.0.1:5186/auth/dashboard',
    VITE_DEV_SERVER_URL: 'http://127.0.0.1:5186',
    USE_GRPC_MANUAL_PIPELINE: 'false', USE_GRPC_AUTO_PIPELINE: 'false', USE_GRPC_CLOUD_CONTEXT_PIPELINE: 'false',
    ELECTRON_GRPC_REALTIME_ENABLED: 'false', ELECTRON_GRPC_AUDIO_ENABLED: 'false',
    ELECTRON_GRPC_REALTIME_HOST: '127.0.0.1', ELECTRON_GRPC_REALTIME_PORT: '1',
  }
  const packaged = process.env.C132_PACKAGED_EXE
  if (packaged) delete isolated.VITE_DEV_SERVER_URL
  const physical = process.env.C132_PHYSICAL_ACCEPTANCE === 'true'
  if (native.hosted) {
    Object.assign(isolated, { ELECTRON_HOSTED_AUDIO_ENABLED: 'true',
      ELECTRON_HOSTED_AUDIO_URL: native.hosted.url, ELECTRON_HOSTED_AUDIO_DEPLOYMENT_ID: native.hosted.deployment,
      C132_HOSTED_ACCEPTANCE: 'true', USE_GRPC_AUTO_PIPELINE: 'true', USE_GRPC_CLOUD_CONTEXT_PIPELINE: 'true',
      ELECTRON_GRPC_REALTIME_ENABLED: 'true', ELECTRON_GRPC_AUDIO_ENABLED: 'true' })
    test.setTimeout(150000)
  }
  if (physical) {
    test.setTimeout(3600000)
    Object.assign(isolated, { USE_GRPC_AUTO_PIPELINE: 'true', USE_GRPC_CLOUD_CONTEXT_PIPELINE: 'true',
      ELECTRON_GRPC_REALTIME_ENABLED: 'true', ELECTRON_GRPC_AUDIO_ENABLED: 'true',
      ...(native.hosted ? {} : { ELECTRON_GRPC_REALTIME_PORT: String(native.grpcPort) }) })
  }
  const checkSecondClient = async () => {
    const secondDirectory = await mkdtemp(path.join(os.tmpdir(), 'c132-second-electron-'))
    let second
    try {
      second = await electron.launch({ executablePath: packaged, args: [], env: { ...isolated, C132_ELECTRON_DATA: secondDirectory,
        ...(native.hosted ? { ELECTRON_HOSTED_AUDIO_URL: native.hosted.secondUrl } : {}) } })
      const other = await second.firstWindow()
      await expect(other.getByText('Current plan: Free', { exact: true })).toBeVisible()
      const status = await other.evaluate(sessionId => window.electronAPI.connectGrpcAutoPipeline({ activeSessionId: sessionId, source: 'microphone' }), native.manual.session_id)
      expect(status.autoPipelineReady).not.toBe(true)
      expect(JSON.stringify(status)).toContain('subscription_auto_busy')
      console.log('Second packaged account run correctly denied.')
    } finally {
      if (second) await second.close()
      await rm(secondDirectory, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 })
    }
  }
  let app
  try {
    app = await electron.launch({ ...(packaged ? { executablePath: packaged, args: [] } : { args: [path.resolve('tests/catalog/fixtures/electron-subscription.cjs')] }), env: isolated })
    let page = await app.firstWindow()
    if (packaged) {
      expect(await app.evaluate(({ app }) => app.isPackaged)).toBe(true)
      await expect(page).toHaveURL(/^file:/)
    }
    await expect(page.getByText('Current plan: Free', { exact: true })).toBeVisible({ timeout: 30000 })
    await page.getByRole('button', { name: 'Upgrade', exact: true }).click()
    await expect.poll(() => app.evaluate(() => global.subscriptionOpened)).toEqual(['http://127.0.0.1:5186/#pricing'])
    expect(await page.evaluate(() => typeof window.electronAPI.getSubscription)).toBe('function')
    expect(await page.getByRole('heading', { name: 'Plus', exact: true }).count()).toBe(0)
    await mkdir('../docs/assets/subscriptions', { recursive: true })
    await page.screenshot({ path: `../docs/assets/subscriptions/c132-${packaged ? 'packaged' : 'electron'}-current-plan.png` })
    const transcript = await page.evaluate(() => window.electronAPI.transcribeAudio({ bytes: new Uint8Array([0, 0, 1, 0]), contentType: 'audio/wav' }))
    expect(transcript.ok).toBe(true)
    expect(transcript.payload.text).toBe('Synthetic desktop transcription')
    if (native.hosted && !physical) {
      await page.addScriptTag({ path: path.resolve('../tmp/c132-physical-panel/physical-auto.iife.js') })
      // Deterministic capture substitute, not physical loopback acceptance.
      await page.evaluate(sessionId => {
        window.hostedTracks = []
        const getUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices)
        navigator.mediaDevices.getUserMedia = async constraints => {
          const stream = await getUserMedia(constraints)
          window.hostedTracks.push(...stream.getTracks())
          return stream
        }
        navigator.mediaDevices.getDisplayMedia = async () => {
          const context = new AudioContext(), destination = context.createMediaStreamDestination()
          const oscillator = context.createOscillator(); oscillator.connect(destination); oscillator.start()
          const track = destination.stream.getAudioTracks()[0], stop = track.stop.bind(track)
          window.hostedTracks.push(track)
          track.stop = () => { stop(); oscillator.stop(); void context.close() }
          return destination.stream
        }
        window.installPhysicalAcceptance({ sessionId, hosted: true, synthetic: true })
      }, native.manual.session_id)
      const health = await page.evaluate(() => window.electronAPI.checkGrpcRealtimeHealth())
      expect(health.grpc_health).toBe('healthy')
      for (const source of ['microphone', 'system', 'both']) {
        await page.getByRole('button', { name: `Start ${source}`, exact: true }).click()
        try { await expect.poll(async () => {
          const value = await page.evaluate(() => window.electronAPI.getGrpcRealtimeStatus())
          if (value.connectionStatus === 'error') throw Error(`Safe hosted failure: ${value.grpc_last_failure_reason}`)
          return value.answerCompletedCount
        }, { timeout: 25000 }).toBe(1) } catch {
          const value = await page.evaluate(() => window.electronAPI.getGrpcRealtimeStatus())
          throw Error(JSON.stringify({ source, connection: value.connectionStatus, ready: value.autoPipelineReady, chunks: value.audioChunksSent, failure: value.grpc_last_failure_reason, answerFailure: value.answerFailureCode, questions: value.questionsDetectedCount, answers: value.answerCompletedCount, panel: await page.locator('section[aria-label="Isolated physical acceptance"] pre').textContent() }))
        }
        const state = await page.evaluate(() => window.electronAPI.getGrpcRealtimeStatus())
        expect(state.clientAudioRelay).toBe(true)
        expect(state.answerStreamVersion).toBe(1)
        expect(JSON.stringify(state)).not.toMatch(/Bearer |owner_token|claim_token|synthetic-only/)
        if (source === 'microphone') await checkSecondClient()
        await page.getByRole('button', { name: 'Stop', exact: true }).click()
        await expect.poll(async () => (await page.evaluate(() => window.electronAPI.getSubscription())).auto.reserved).toBe('0')
        await expect.poll(() => page.evaluate(() => window.hostedTracks.every(track => track.readyState === 'ended'))).toBe(true)
      }
      // Kill only the registered disposable relay worker after a durable answer.
      await page.getByRole('button', { name: 'Start microphone', exact: true }).click()
      await expect.poll(async () => (await page.evaluate(() => window.electronAPI.getGrpcRealtimeStatus())).answerCompletedCount).toBe(1)
      execFileSync('taskkill.exe', ['/PID', String(native.hosted.workers[0]), '/T', '/F'], { encoding: 'utf8' })
      await expect.poll(() => page.evaluate(() => window.hostedTracks.every(track => track.readyState === 'ended')), { timeout: 10000 }).toBe(true)
      await expect.poll(async () => (await page.evaluate(() => window.electronAPI.getSubscription())).auto.reserved, { timeout: 20000 }).toBe('0')
      // No automatic reconnect. A deliberate fresh start uses the second worker.
      await app.evaluate((_electron, url) => { process.env.ELECTRON_HOSTED_AUDIO_URL = url }, native.hosted.secondUrl)
      await page.getByRole('button', { name: 'Stop', exact: true }).click()
      await page.evaluate(() => window.electronAPI.checkGrpcRealtimeHealth())
      await page.getByRole('button', { name: 'Start microphone', exact: true }).click()
      await expect.poll(async () => (await page.evaluate(() => window.electronAPI.getGrpcRealtimeStatus())).answerCompletedCount).toBe(1)
      await page.getByRole('button', { name: 'Stop', exact: true }).click()
      const usage = await page.evaluate(() => window.electronAPI.getSubscription())
      expect(BigInt(usage.auto.used)).toBeGreaterThan(0n)
      expect(BigInt(usage.auto.used)).toBeLessThanOrEqual(600000000n)
      await page.screenshot({ path: '../docs/assets/subscriptions/c132-hosted-electron.png' })
    }
    if (physical) {
      await page.addScriptTag({ path: path.resolve('../tmp/c132-physical-panel/physical-auto.iife.js') })
      await page.evaluate(({ sessionId, hosted }) => window.installPhysicalAcceptance({ sessionId, hosted }), { sessionId: native.manual.session_id, hosted: Boolean(native.hosted) })
      const restartDesktop = async () => {
        const before = await page.evaluate(() => window.electronAPI.getSubscription())
        expect(before.ok).toBe(true)
        expect(BigInt(before.auto.used)).toBeGreaterThan(0n)
        // Ask the connected Electron main for its actual PID; the launch-process
        // handle can name a Windows command wrapper. Register close before kill.
        const ownedMainPid = await app.evaluate(() => process.pid)
        const closed = app.waitForEvent('close', { timeout: 15000 })
        let terminationError
        try { execFileSync('taskkill.exe', ['/PID', String(ownedMainPid), '/T', '/F'], { encoding: 'utf8' }) }
        catch (error) { terminationError = error }
        await closed
        // Windows can report a child disappearing during tree termination as
        // failure. Do not accept that exit status blindly: verify main and every
        // reported child are gone; EPERM or a surviving process still fails.
        const ownedPids = new Set([ownedMainPid, ...[...String(terminationError?.stderr || '').matchAll(/process with PID (\d+)/g)].map(match => Number(match[1]))])
        for (const pid of ownedPids) await expect.poll(() => {
          try { process.kill(pid, 0); return false } catch (error) {
            if (error.code === 'ESRCH') return true
            throw error
          }
        }, { timeout: 5000 }).toBe(true)
        app = await electron.launch({ executablePath: packaged, args: [], env: isolated })
        page = await app.firstWindow()
        await expect(page.getByText('Current plan: Free', { exact: true })).toBeVisible()
        await expect(page).toHaveURL(/^file:/)
        await expect.poll(async () => page.evaluate(() => window.electronAPI.getSubscription()).then(result => result.auto?.reserved), { timeout: 20000 }).toBe('0')
        const after = await page.evaluate(() => window.electronAPI.getSubscription())
        expect(after.plan.offer_version_id).toBe(before.plan.offer_version_id)
        expect(BigInt(after.auto.used)).toBeGreaterThanOrEqual(BigInt(before.auto.used))
        expect((await page.evaluate(() => window.electronAPI.getGrpcRealtimeStatus())).autoPipelineReady).not.toBe(true)
        await page.addScriptTag({ path: path.resolve('../tmp/c132-physical-panel/physical-auto.iife.js') })
        await page.evaluate(({ sessionId, hosted }) => window.installPhysicalAcceptance({ sessionId, hosted }), { sessionId: native.manual.session_id, hosted: Boolean(native.hosted) })
        await page.bringToFront()
        await writeFile(`${process.env.C132_MANUAL_STOP}.restart.json`, JSON.stringify({
          completedAt: new Date().toISOString(), pid: app.process().pid,
          sameOffer: true, usedBefore: before.auto.used, usedAfter: after.auto.used,
          reservedAfter: after.auto.reserved, autoResumed: false,
        }, null, 2))
        console.log('Owned desktop tree restarted; same offer and consumed usage retained; capture did not resume.')
      }
      if (process.env.C132_CAPTURE_SMOKE === 'true') {
        for (const source of ['microphone', 'system', 'both']) {
          await page.getByRole('button', { name: `Start ${source}`, exact: true }).click()
          await expect(page.getByRole('button', { name: `Start ${source}`, exact: true })).toBeEnabled()
          try { await expect.poll(async () => page.evaluate(() => window.electronAPI.getGrpcRealtimeStatus()).then(status =>
            status.autoPipelineReady && (source === 'microphone' ? status.audioChunksSent > 2 : Boolean(status.systemAudio?.system_first_chunk_sent_to_grpc_at))),
          { timeout: 15000 }).toBe(true) } catch (error) {
            const status = await page.evaluate(() => window.electronAPI.getGrpcRealtimeStatus())
            console.log(JSON.stringify({ source, ready: status.autoPipelineReady, failure: status.grpc_last_failure_reason, auto: status.autoStatus, system: status.systemAudio, sent: status.audioChunksSent }))
            console.log('Safe physical panel:', await page.getByRole('region', { name: 'Isolated physical acceptance' }).locator('pre').textContent())
            throw error
          }
          if (source === 'microphone' && process.env.C132_COMPETE_SMOKE === 'true') await checkSecondClient()
          if (source === 'microphone' && process.env.C132_RESTART_SMOKE === 'true') {
            // Settle a real first run so restart must retain non-zero prior use,
            // rather than passing a vacuous comparison against a zero baseline.
            await page.getByRole('button', { name: 'Stop', exact: true }).click()
            await expect(page.getByRole('button', { name: 'Stop', exact: true })).toBeEnabled()
            expect(BigInt((await page.evaluate(() => window.electronAPI.getSubscription())).auto.used)).toBeGreaterThan(0n)
            await page.getByRole('button', { name: 'Start microphone', exact: true }).click()
            await expect(page.getByRole('button', { name: 'Start microphone', exact: true })).toBeEnabled()
            await expect.poll(async () => page.evaluate(() => window.electronAPI.getGrpcRealtimeStatus()).then(status => status.autoPipelineReady && status.audioChunksSent > 2), { timeout: 15000 }).toBe(true)
            await restartDesktop()
          }
          await page.getByRole('button', { name: 'Stop', exact: true }).click()
          await expect(page.getByRole('button', { name: 'Stop', exact: true })).toBeEnabled()
          await expect.poll(async () => page.evaluate(() => window.electronAPI.getGrpcRealtimeStatus()).then(status => status.autoPipelineReady)).toBe(false)
          console.log(`Packaged physical ${source} delivered PCM and stopped; no real STT/provider.`)
        }
      }
      const collectTiming = async () => {
        const result = await page.evaluate(() => window.physicalTimingResult)
        if (!result || result.collected) return
        await writeFile(`${process.env.C132_MANUAL_STOP}.timing-raw.json`, JSON.stringify(result, null, 2))
        const used = (BigInt(result.final.auto.used) - BigInt(result.baseline.auto.used)) / 1000n
        expect(result.final.auto.reserved).toBe('0')
        expect(result.capture_started_ms).toBeGreaterThanOrEqual(result.authorization_confirmed_ms)
        expect(result.capture_first_frame_ms).toBeGreaterThanOrEqual(result.capture_started_ms)
        const lower = result.local_forwarding_revoked_ms - result.authorization_confirmed_ms
        const upper = result.server_stop_ack_ms - result.authorization_request_ms
        expect(Number(used)).toBeGreaterThanOrEqual(lower - result.tolerance_ms)
        expect(Number(used)).toBeLessThanOrEqual(upper + result.tolerance_ms)
        await writeFile(`${process.env.C132_MANUAL_STOP}.timing.json`, JSON.stringify({
          ...result, charged_ms: Number(used), lower_bound_ms: lower, upper_bound_ms: upper,
          captured_ms: result.local_forwarding_revoked_ms - result.capture_started_ms,
          startup_ms: result.authorization_confirmed_ms - result.authorization_request_ms,
          stop_round_trip_ms: result.server_stop_ack_ms - result.local_forwarding_revoked_ms,
          comparison: 'within-predeclared-authorization-bounds',
        }, null, 2))
        await page.evaluate(() => { window.physicalTimingResult.collected = true })
        console.log('Synchronized physical timing: charge within independent monotonic authorization bounds; zero reservation.')
      }
      if (process.env.C132_TIMING_SMOKE === 'true') {
        await page.getByRole('button', { name: 'Start synchronized 120-second silence check', exact: true }).click()
        await expect.poll(() => page.evaluate(() => Boolean(window.physicalTimingResult)), { timeout: 135000 }).toBe(true)
        await collectTiming()
      }
      if (process.env.C132_PHYSICAL_SMOKE !== 'true') {
        if (native.hosted) {
          const health = await page.evaluate(() => window.electronAPI.checkGrpcRealtimeHealth())
          expect(health.clientAudioRelay).toBe(true)
          expect(health.grpc_health).toBe('healthy')
          expect(health.grpc_auto_available).toBe(true)
        }
        await page.bringToFront()
        await expect(page.getByRole('button', { name: 'Start microphone', exact: true })).toBeEnabled()
        await page.screenshot({ path: `${process.env.C132_MANUAL_STOP}.ready.png` })
        await writeFile(`${process.env.C132_MANUAL_STOP}.ready.json`, JSON.stringify({
          environment: 'isolated-physical-acceptance', transport: native.hosted ? 'hosted-relay' : 'local-grpc', readyAt: new Date().toISOString(),
          packaged: await app.evaluate(({ app }) => app.isPackaged),
          compiledRenderer: page.url().startsWith('file:'), pid: app.process().pid,
          syntheticAccount: true, localDisposableDatabase: true, realProviders: false,
          expiresAfterMinutes: 58,
        }, null, 2))
        console.log('Isolated packaged physical setup ready. Complete the manual checklist; create the documented stop marker to finish.')
        await expect.poll(async () => {
          await collectTiming()
          const control = `${process.env.C132_MANUAL_STOP}.control`
          let command
          try { command = (await readFile(control, 'utf8')).trim(); await unlink(control) } catch { /* No requested fault. */ }
          if (command === 'expire') await app.evaluate(() => {
            global.subscriptionHeartbeatTimers.forEach(clearInterval)
            global.subscriptionHeartbeatTimers = []
          })
          if (command === 'compete') await checkSecondClient()
          if (command === 'restart') await restartDesktop()
          try { await access(process.env.C132_MANUAL_STOP); return true } catch { return false }
        }, { timeout: 3500000, intervals: [1000] }).toBe(true)
      }
      await page.getByRole('button', { name: 'Stop', exact: true }).click()
    }
    await page.evaluate(() => window.electronAPI.logoutAuth())
    await expect(page.getByText('Current plan: Free', { exact: true })).toHaveCount(0)
    const result = await page.evaluate(() => window.electronAPI.getSubscription())
    expect(result.ok).not.toBe(true)
  } finally {
    if (app) await app.close()
    // Chromium can release its Windows profile locks just after app.close().
    // Native bounded EBUSY retries preserve failures if the lock persists.
    await rm(directory, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 })
  }
})
