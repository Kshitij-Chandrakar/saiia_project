import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const overlaySource = readFileSync(new URL('./components/OverlayWindow.jsx', import.meta.url), 'utf8')
const answerPanelSource = readFileSync(new URL('./components/AnswerPanel.jsx', import.meta.url), 'utf8')
const diagnosticsSource = readFileSync(new URL('./components/MainDiagnosticsWindow.jsx', import.meta.url), 'utf8')
const appSource = readFileSync(new URL('./App.jsx', import.meta.url), 'utf8')
const mainSource = readFileSync(new URL('../electron/main.cjs', import.meta.url), 'utf8')
const stylesSource = readFileSync(new URL('./styles/glass.css', import.meta.url), 'utf8')

function sourceBetween(source, start, end) {
  const startIndex = source.indexOf(start)
  assert.ok(startIndex >= 0, `missing source marker: ${start}`)
  const endIndex = source.indexOf(end, startIndex + start.length)
  assert.ok(endIndex > startIndex, `missing source end marker: ${end}`)
  return source.slice(startIndex, endIndex)
}

test('Analyze Screen toolbar button starts OCR directly', () => {
  const clickHandler = sourceBetween(
    overlaySource,
    'const handleAnalyzeScreen = useCallback(() => {',
    'const handleAnalyzeMenuKeyDown'
  )

  assert.match(clickHandler, /setActiveTab\('analyzeScreen'\)/)
  assert.match(clickHandler, /setAnalyzeMenuOpen\(false\)/)
  assert.match(clickHandler, /triggerToolbarAction\('analyze-screen-ocr'/)
  assert.doesNotMatch(clickHandler, /handleScreenCapture/)
})

test('Analyze Screen toolbar action starts OCR capture', () => {
  const appAnalyzeBranch = sourceBetween(
    appSource,
    "if (action === 'analyze-screen') {",
    "if (action === 'analyze-screen-ocr') {"
  )

  assert.match(appAnalyzeBranch, /await handleScreenCapture\(\)/)
  assert.match(appAnalyzeBranch, /return/)
  assert.doesNotMatch(appAnalyzeBranch, /handleGenerateFromProvidedScreenText/)
  assert.doesNotMatch(appAnalyzeBranch, /classifyAndGenerate/)
  assert.doesNotMatch(appAnalyzeBranch, /appendQuestionHistory/)
})

test('OCR menu selection is the only topbar path that starts existing screen capture', () => {
  assert.equal((overlaySource.match(/handleAnalyzeMenuAction\('analyze-screen-ocr'\)/g) || []).length, 1)
  assert.match(appSource, /if \(action === 'analyze-screen-ocr'\) \{\s*await handleScreenCapture\(\)\s*return\s*\}/)
  assert.match(answerPanelSource, /triggerToolbarAction\?\.\('analyze-screen-ocr'/)
})

test('OCR active path uses one capture and one direct screen-model request', () => {
  const handler = sourceBetween(
    appSource,
    'const handleScreenCapture = async () => {',
    'const handleManualQuestionSubmit = async (nextText) => {'
  )

  assert.match(handler, /await window\.saiia\.captureActiveWindow\(\)/)
  assert.match(appSource, /\/api\/screen\/analyze-active-window-answer/)
  assert.match(handler, /requestActiveWindowAnswer/)
  assert.match(handler, /commitDirectScreenAnswer/)
  assert.doesNotMatch(handler, /await loadScreenSourceRecoveryOptions\(\)/)
  assert.doesNotMatch(handler, /captureActiveWindowSequence/)
  assert.doesNotMatch(handler, /captureItems/)
  assert.doesNotMatch(handler, /perCaptureAnalyses/)
  assert.doesNotMatch(handler, /mergeScreenProblemText/)
  assert.doesNotMatch(handler, /analyzeActiveWindowBlob/)
  assert.doesNotMatch(handler, /handleGenerateFromProvidedScreenText/)
})

test('normal active-window OCR freezes foreground before hiding, then falls back after hide', () => {
  const activeCaptureHandler = sourceBetween(
    mainSource,
    'async function captureActiveWindowSource() {',
    'async function captureActiveWindowSequence() {'
  )

  assert.match(activeCaptureHandler, /let preHideTarget = null/)
  assert.match(activeCaptureHandler, /allowCachedFallback:\s*false/)
  assert.match(activeCaptureHandler, /allowDesktopFallback:\s*false/)
  assert.match(activeCaptureHandler, /withSaiiaWindowsHidden\(async \(\) => \{/)
  assert.match(activeCaptureHandler, /const frozenTarget = preHideTarget \|\| \(await resolveCaptureTargetForAnalyze\(\)\)/)
})

test('active-window resolver carries native window identity into source matching', () => {
  assert.match(mainSource, /nativeWindowId = \$hwnd\.ToInt64\(\)\.ToString\(\)/)
  assert.match(mainSource, /nativeWindowId:\s*String\(payload\?\.nativeWindowId/)
  assert.match(mainSource, /nativeWindowId:\s*String\(extras\.nativeWindowId \|\| snapshot\.nativeWindowId/)
  assert.match(mainSource, /function sourceMatchesNativeWindow\(sourceId, nativeWindowId\)/)
  assert.match(mainSource, /source\.startsWith\(`window:\$\{nativeId\}:`\)/)
  assert.match(mainSource, /sourceMatchesNativeWindow\(source\.id, targetWindow\?\.nativeWindowId\)/)
  assert.match(mainSource, /function redactWindowTitleForDiagnostics\(value\)/)
  assert.match(mainSource, /current_active_window_title:\s*redactWindowTitleForDiagnostics\(currentActiveTitle\)/)
})

test('active-window resolver does not prefer stale browser cache over exact foreground identity', () => {
  const preferStored = sourceBetween(
    mainSource,
    'function shouldPreferStoredTarget(currentSnapshot, storedTarget) {',
    'function isUsableExternalSnapshot(snapshot) {'
  )
  const resolver = sourceBetween(
    mainSource,
    'async function resolveCaptureTargetForAnalyze(options = {}) {',
    'async function captureActiveWindowSource() {'
  )

  assert.match(mainSource, /const LAST_EXTERNAL_TARGET_TTL_MS = 30000/)
  assert.match(preferStored, /if \(currentSnapshot\.nativeWindowId\) \{\s*return false\s*\}/)
  assert.ok(
    resolver.indexOf('if (isUsableExternalSnapshot(foregroundWindow))') <
      resolver.indexOf('shouldPreferStoredTarget(foregroundWindow, freshTarget)'),
    'verified foreground target must win before recent cached target'
  )
  assert.match(resolver, /refreshForegroundWindowSnapshot\(\{ force: true \}\)/)
})

test('active-window resolver fails controlled instead of choosing ambiguous source order', () => {
  const fallback = sourceBetween(
    mainSource,
    'async function getBestExternalDesktopSourceCandidate() {',
    'async function resolveCaptureTargetForAnalyze(options = {}) {'
  )
  const handler = sourceBetween(
    appSource,
    'const handleScreenCapture = async () => {',
    'const handleManualQuestionSubmit = async (nextText) => {'
  )

  assert.match(fallback, /candidateCount \+= 1/)
  assert.match(fallback, /candidateCount !== 1/)
  assert.match(fallback, /active_window_ambiguous/)
  assert.match(
    mainSource,
    /SAIIA could not identify the active question window\./
  )
  assert.match(handler, /Could not identify active window\. Waiting for retry\./)
})

test('OCR panel no longer exposes preview edit or generate-from-preview controls', () => {
  assert.doesNotMatch(answerPanelSource, /Generate Answer from Screen Text/)
  assert.doesNotMatch(answerPanelSource, /Screen Preview:/)
  assert.doesNotMatch(answerPanelSource, /Back\/Edit Question/)
  assert.doesNotMatch(answerPanelSource, /topbar-screen-panel__textarea/)
  assert.match(answerPanelSource, /Analyze Screen/)
  assert.match(answerPanelSource, />\s*Extension\s*</)
})

test('OCR success controls are contextual', () => {
  const successPanel = sourceBetween(
    answerPanelSource,
    '<div className="topbar-screen-panel__actions">',
    '<span className="topbar-answer-panel__label">Screen Answer:</span>'
  )

  assert.match(successPanel, /copyableScreenCode\.code \?/)
  assert.match(successPanel, /Copy Code/)
  assert.match(successPanel, /Analyze Screen/)
  assert.match(successPanel, />\s*Extension\s*</)
  assert.doesNotMatch(successPanel, /Copy Answer/)
  assert.doesNotMatch(successPanel, /Analyze Again/)
  assert.doesNotMatch(successPanel, /Clear Result/)
  assert.doesNotMatch(successPanel, /Try OCR Again/)
  assert.doesNotMatch(successPanel, /Use Extension/)
})

test('OCR failure controls use the same Analyze Screen and Extension actions', () => {
  const failureControls = sourceBetween(
    answerPanelSource,
    '<span className="topbar-answer-panel__label">Screen Answer:</span>',
    '              </>\n            )}'
  )

  assert.match(failureControls, /Analyze Screen/)
  assert.match(failureControls, /onClick=\{handleUseExtension\}/)
  assert.match(failureControls, />\s*Extension\s*</)
  assert.doesNotMatch(answerPanelSource, /Choose Screen Source/)
  assert.doesNotMatch(answerPanelSource, /Choose Screen:/)
  assert.doesNotMatch(answerPanelSource, /triggerToolbarAction\?\.\('choose-screen-source'/)
  assert.doesNotMatch(failureControls, /Try OCR Again/)
  assert.doesNotMatch(failureControls, /Use Extension/)
  assert.doesNotMatch(failureControls, /Clear Result/)
  assert.doesNotMatch(failureControls, /Copy Answer/)
  assert.doesNotMatch(failureControls, /Analyze Again/)
  assert.doesNotMatch(failureControls, /Copy Code/)
})

test('Analyze Screen empty state hides idle placeholder text', () => {
  const emptyStatePanel = sourceBetween(
    answerPanelSource,
    '<span className="topbar-answer-panel__label">Screen Answer:</span>',
    '<div className="topbar-screen-panel__actions">'
  )

  assert.doesNotMatch(answerPanelSource, /No screen answer yet\. Use OCR to analyze the active window\./)
  assert.doesNotMatch(answerPanelSource, /Screen confidence: Not available/)
  assert.doesNotMatch(answerPanelSource, /Waiting for a question\.\.\./)
  assert.doesNotMatch(emptyStatePanel, /screenError/)
})

test('manual typed questions use the Chat display route', () => {
  const manualSubmit = sourceBetween(
    appSource,
    'const handleManualQuestionSubmit = async (nextText) => {',
    'const handleGenerateFromProvidedScreenText = async (nextText, options = {}) => {'
  )

  assert.match(manualSubmit, /setAnswerDisplayMode\('chat'\)/)
  assert.match(manualSubmit, /mode: 'chat'/)
  assert.doesNotMatch(manualSubmit, /setAnswerDisplayMode\('answer'\)/)
  assert.doesNotMatch(manualSubmit, /mode: 'manual'/)
})

test('Answer and Chat toolbar buttons explicitly own their panels', () => {
  const answerHandler = sourceBetween(
    overlaySource,
    'const handleAiHelp = async () => {',
    'const handleChat = () => {'
  )
  const chatHandler = sourceBetween(
    overlaySource,
    'const handleChat = () => {',
    "const menuHeaderText = overlayState.provider"
  )
  const focusEffect = sourceBetween(
    overlaySource,
    'const nextAutoFocusAnswerKey = overlayState.answer',
    '  }, [overlayState, activeTab])'
  )

  assert.match(answerHandler, /setActiveTab\('aiHelp'\)/)
  assert.match(answerHandler, /setAnalyzeMenuOpen\(false\)/)
  assert.match(chatHandler, /setActiveTab\('chat'\)/)
  assert.doesNotMatch(chatHandler, /prev\) => \(prev === 'chat' \? null : 'chat'\)/)
  assert.match(focusEffect, /lastAutoFocusAnswerKeyRef\.current !== nextAutoFocusAnswerKey/)
  assert.match(overlaySource, /active=\{activeTab === 'analyzeScreen'\}/)
  assert.doesNotMatch(overlaySource, /activeTab === 'analyzeScreen' \|\| overlayState\.ocrProcessing/)
})

test('runtime diagnostics screen controls use the same contextual matrix', () => {
  const normalizedDiagnosticsSource = diagnosticsSource.replace(/\r\n/g, '\n')
  const successControls = sourceBetween(
    normalizedDiagnosticsSource,
    '<div className="form-actions" style={{ marginTop:',
    '                  ) : ('
  )
  const emptyControls = sourceBetween(
    normalizedDiagnosticsSource,
    '<div className="form-actions">\n                        <button',
    '                    </>'
  )

  assert.match(successControls, /copyableScreenCode\.code \?/)
  assert.match(successControls, /Copy Code/)
  assert.match(successControls, /Analyze Screen/)
  assert.match(successControls, />\s*Extension\s*</)
  assert.doesNotMatch(successControls, /Copy Answer/)
  assert.doesNotMatch(successControls, /Clear Screen Result/)
  assert.match(emptyControls, /Analyze Screen/)
  assert.match(emptyControls, />\s*Extension\s*</)
  assert.doesNotMatch(emptyControls, /Clear Screen Result/)
})

test('OCR timing metadata is collected and shown in diagnostics', () => {
  assert.match(appSource, /image_prepare_ms/)
  assert.match(appSource, /screen_model_ms/)
  assert.match(appSource, /response_parse_ms/)
  assert.match(appSource, /overlay_render_ms/)
  assert.match(appSource, /screen_model_request_count/)
  assert.match(appSource, /questions_answered/)
  assert.match(appSource, /incomplete_questions_ignored/)
  assert.match(appSource, /automatic_fallback_count/)
  assert.match(appSource, /correction_request_count/)
  assert.match(appSource, /encoded_image_bytes/)
  assert.match(answerPanelSource + readFileSync(new URL('./components/MainDiagnosticsWindow.jsx', import.meta.url), 'utf8'), /Screen model requests/)
  assert.match(answerPanelSource + readFileSync(new URL('./components/MainDiagnosticsWindow.jsx', import.meta.url), 'utf8'), /Questions answered/)
  assert.doesNotMatch(readFileSync(new URL('./components/MainDiagnosticsWindow.jsx', import.meta.url), 'utf8'), /label="Vision time"/)
  assert.doesNotMatch(readFileSync(new URL('./components/MainDiagnosticsWindow.jsx', import.meta.url), 'utf8'), /label="Generation time"/)
})

test('OCR batch answers are stored and rendered as one screen operation', () => {
  const commit = sourceBetween(
    appSource,
    'const commitDirectScreenAnswer = (payload, { operation, pipelineStarted }) => {',
    'const handleElectronScreenSourceCapture = async (sourceId) => {'
  )

  assert.match(commit, /canCommitScreenResult/)
  assert.match(commit, /markScreenOperationCommitted\(operation\.operationId\)/)
  assert.match(commit, /payload\.result_mode/)
  assert.match(commit, /normalizeScreenResponse\(payload\)/)
  assert.match(commit, /screenEnvelope/)
  assert.match(commit, /payload\.items/)
  assert.match(commit, /question_count/)
  assert.match(commit, /incomplete_question_count/)
  assert.match(commit, /screenAnswerItems/)
  assert.match(commit, /screenEnvelope/)
  assert.match(commit, /sourceType: screenEnvelope\.source_type/)
  assert.match(commit, /appendQuestionHistoryEntry/)
  assert.equal((commit.match(/appendQuestionHistoryEntry/g) || []).length, 1)
  assert.match(commit, /generation_request_count \|\| 0/)
  assert.match(commit, /primary_generation_ms:\s*null/)
  assert.match(answerPanelSource, /screenBatchResult/)
  assert.match(answerPanelSource, /Screen Answers:/)
  assert.doesNotMatch(answerPanelSource, /copyToClipboard\(effectiveScreenAnswerText\)/)
  assert.match(answerPanelSource, /copyableScreenCode\.code \?/)
})

test('Extension menu selection reports unavailable without capture, generation, fake status, or history', () => {
  const extensionBranch = sourceBetween(
    appSource,
    "if (action === 'analyze-screen-extension') {",
    "if (action === 'capture-screen-source') {"
  )
  const extensionMenu = sourceBetween(
    overlaySource,
    "handleAnalyzeMenuAction('analyze-screen-extension')",
    '</button>'
  )

  assert.match(extensionBranch, /Browser extension connection is not available yet\./)
  assert.match(extensionBranch, /beginScreenOperation\('browser_extension'\)/)
  assert.match(extensionBranch, /requestExtensionUnavailable\(operation\)/)
  assert.match(extensionBranch, /failCurrentScreenOperation\(operation/)
  assert.match(extensionBranch, /setAnswerDisplayMode\('screen'\)/)
  assert.match(extensionBranch, /setOcrProcessing\(false\)/)
  assert.match(extensionBranch, /setScreenAnswerLoading\(false\)/)
  assert.doesNotMatch(extensionBranch, /handleScreenCapture/)
  assert.doesNotMatch(extensionBranch, /handleGenerateFromProvidedScreenText/)
  assert.doesNotMatch(extensionBranch, /classifyAndGenerate/)
  assert.doesNotMatch(extensionBranch, /appendQuestionHistory/)
  assert.match(extensionMenu, /Extension setup required/)
  assert.doesNotMatch(extensionMenu, /Connected/)
  assert.doesNotMatch(appSource, /action === 'generate-screen-text'/)
  assert.doesNotMatch(appSource, /action === 'back-edit-screen-text'/)
})

test('Analyze Screen menu has keyboard, focus-return, and outside-click handling', () => {
  assert.match(overlaySource, /event\.key === 'Escape'/)
  assert.match(overlaySource, /event\.key === 'ArrowDown' \|\| event\.key === 'ArrowUp'/)
  assert.match(overlaySource, /analyzeMenuItemRefs\.current\[0\]\?\.focus\(\)/)
  assert.match(overlaySource, /analyzeButtonRef\.current\?\.focus\(\)/)
  assert.match(overlaySource, /window\.addEventListener\('pointerdown', handlePointerDown\)/)
  assert.match(overlaySource, /closeAnalyzeMenu\(true\)/)
})

test('Ctrl+Shift+Enter starts Analyze Screen OCR directly', () => {
  assert.match(mainSource, /globalShortcut\.register\('Control\+Shift\+Enter'[\s\S]*broadcastToolbarAction\('analyze-screen'\)/)
  assert.match(overlaySource, /payload\?\.action === 'analyze-screen'[\s\S]*setActiveTab\('analyzeScreen'\)/)
  assert.match(
    sourceBetween(appSource, "if (action === 'analyze-screen') {", "if (action === 'analyze-screen-ocr') {"),
    /await handleScreenCapture\(\)/
  )
})

test('Analyze Screen menu uses existing compact topbar visual system', () => {
  assert.match(stylesSource, /\.topbar-analyze-menu\s*\{[\s\S]*background:\s*rgba\(19, 21, 24, 0\.98\)/)
  assert.match(stylesSource, /\.topbar-toolbar-shell:has\(\.topbar-menu\),\s*\.topbar-toolbar-shell:has\(\.topbar-analyze-menu\)/)
  assert.match(stylesSource, /\.topbar-analyze-menu__item:focus-visible/)
})

test('Analyze Screen and Chat panels cannot resize below their content minimum', () => {
  assert.match(answerPanelSource, /mode === 'analyzeScreen' \|\| mode === 'chat' \? 320 : 238/)
  assert.match(answerPanelSource, /minHeight:\s*minPanelHeight \+ 132/)
  assert.match(mainSource, /requestedMinHeight/)
  assert.match(mainSource, /height:\s*Math\.max\(requestedMinHeight, Math\.min\(requestedHeight, maxHeight\)\)/)
})
