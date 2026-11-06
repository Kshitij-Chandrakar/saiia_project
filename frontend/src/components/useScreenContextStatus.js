import { useEffect, useRef, useState } from 'react'

export function useScreenContextStatus() {
  const [status, setStatus] = useState(null)
  const latest = useRef(-1)
  useEffect(() => {
    let mounted = true
    const accept = value => {
      if (mounted && value && Number.isSafeInteger(value.sequence) && value.sequence >= latest.current) {
        latest.current = value.sequence; setStatus(value)
      }
    }
    const unsubscribe = window.electronAPI?.onScreenContextEvent?.(accept)
    window.electronAPI?.getScreenContextStatus?.().then(accept).catch(() => {})
    return () => { mounted = false; unsubscribe?.() }
  }, [])
  return status
}
