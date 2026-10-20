// Main stamps every publication; subscribe before loading the initial snapshot.
export function mergeOverlaySnapshot(current, next) {
  if (!next || typeof next !== 'object') return current
  if (current.overlayPublicationVersion != null &&
      (!Number.isSafeInteger(next.overlayPublicationVersion) || next.overlayPublicationVersion <= current.overlayPublicationVersion)) return current
  const identity = next.grpcAnswerIdentity, previous = current.grpcAnswerFence || current.grpcAnswerIdentity
  if (identity && (!['accepted_turn', 'display_revision', 'retry_attempt', 'provider_attempt'].every(key =>
      /^(0|[1-9][0-9]{0,19})$/.test(identity[key]) && BigInt(identity[key]) < (1n << BigInt(key.endsWith('attempt') ? 32 : 64))) ||
      ![identity.run, identity.epoch, identity.snapshotVersion].every(Number.isSafeInteger))) return current
  if (identity && previous) {
    const sameRun = identity.run === previous.run && identity.epoch === previous.epoch
    const olderRun = identity.run < previous.run || (identity.run === previous.run && identity.epoch < previous.epoch)
    const olderTurn = sameRun && BigInt(identity.accepted_turn) < BigInt(previous.accepted_turn)
    const sameTurn = sameRun && identity.accepted_turn === previous.accepted_turn
    if (olderRun || olderTurn || (sameRun && identity.sessionId !== previous.sessionId) || (sameRun && current.grpcAnswerInvalidated && BigInt(identity.accepted_turn) <= BigInt(previous.accepted_turn)) ||
        (sameTurn && (identity.requestId !== previous.requestId || identity.retry_attempt !== previous.retry_attempt ||
          BigInt(identity.display_revision) < BigInt(previous.display_revision) ||
          BigInt(identity.provider_attempt) < BigInt(previous.provider_attempt) ||
          (identity.display_revision === previous.display_revision && identity.provider_attempt !== previous.provider_attempt) ||
          identity.snapshotVersion < previous.snapshotVersion || (previous.terminal && !identity.terminal)))) {
      const safe = { ...next }
      for (const key of ['answer', 'fullAnswer', 'codingAnswer', 'answerRevealActive', 'answerFullAvailable', 'transcript', 'provider', 'category', 'grpcAnswerIdentity', 'questionHistory', 'answerDisplayMode', 'autoProcessing', 'generationStarted', 'answerPipelineState', 'autoModeStatus', 'status', 'error', 'generationDiagnostics']) delete safe[key]
      return { ...current, ...safe }
    }
  }
  return { ...current, ...next,
    grpcAnswerFence: identity || previous,
    grpcAnswerInvalidated: identity ? false : Object.hasOwn(next, 'grpcAnswerIdentity') ? true : current.grpcAnswerInvalidated }
}
