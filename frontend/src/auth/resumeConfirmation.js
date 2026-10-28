// Confirmation authorizes only the exact client state the customer reviewed.
// The existing authenticated API remains authoritative for operation eligibility.
export function resumeConfirmationIsCurrent(snapshot, current, operationPending) {
  return Boolean(snapshot && current && !operationPending
    && Object.keys(snapshot).every(key => current[key] === snapshot[key]))
}
