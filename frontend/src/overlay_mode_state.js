export function getPanelOwner(activeTab) {
  if (activeTab === 'chat') {
    return 'chat'
  }
  if (activeTab === 'analyzeScreen') {
    return 'screen'
  }
  return 'answer'
}

export function getTabForAnswerMode(mode) {
  if (mode === 'chat') {
    return 'chat'
  }
  if (mode === 'screen') {
    return 'analyzeScreen'
  }
  return 'aiHelp'
}

export function snapshotOverlayState(overlayState) {
  return { ...overlayState }
}

export function getPanelOverlayState({ activeTab, overlayState, modeSnapshots }) {
  if (!activeTab) {
    return overlayState
  }

  const activeOwner = getPanelOwner(activeTab)
  const liveOwner = getPanelOwner(getTabForAnswerMode(overlayState.answerDisplayMode))

  if (activeOwner === liveOwner) {
    return overlayState
  }

  return modeSnapshots[activeOwner] || overlayState
}

export function getAutoFocusedTabForAnswer({ activeTab, answerDisplayMode, answer }) {
  if (!answer) {
    return null
  }

  const nextTab = getTabForAnswerMode(answerDisplayMode)
  if (activeTab === null || getPanelOwner(activeTab) !== getPanelOwner(nextTab)) {
    return nextTab
  }

  return null
}
