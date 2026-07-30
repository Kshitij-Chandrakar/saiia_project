export function isCurrentRequest(latestRequestId, responseRequestId) {
  return latestRequestId === responseRequestId
}
