const SIGNED_OUT_AUTH_STATE = { status: 'signed-out', email: null }

export function normalizeOverlayAuthState(value) {
  const status = typeof value?.status === 'string' ? value.status : 'signed-out'
  const email = typeof value?.email === 'string' && value.email.trim()
    ? value.email.trim()
    : null
  return { status, email }
}

export function createOverlayAuthStateTracker(applyAuthState) {
  let generation = 0

  return {
    clear() {
      generation += 1
      applyAuthState(SIGNED_OUT_AUTH_STATE)
    },

    async refresh(getAuthState) {
      const requestGeneration = generation + 1
      generation = requestGeneration

      try {
        const nextState = await getAuthState?.()
        if (generation !== requestGeneration) {
          return false
        }
        applyAuthState(normalizeOverlayAuthState(nextState))
        return true
      } catch {
        if (generation !== requestGeneration) {
          return false
        }
        applyAuthState(SIGNED_OUT_AUTH_STATE)
        return true
      }
    },
  }
}
