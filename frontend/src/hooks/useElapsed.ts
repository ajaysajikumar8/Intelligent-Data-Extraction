import { useEffect, useState } from 'react'

/** Whole seconds since `startIso`, ticking every second while `active`. */
export function useElapsedSeconds(startIso: string, active: boolean): number {
  const compute = () => Math.max(0, Math.floor((Date.now() - new Date(startIso).getTime()) / 1000))
  const [seconds, setSeconds] = useState(compute)

  useEffect(() => {
    if (!active) return
    setSeconds(compute())
    const timer = setInterval(() => setSeconds(compute()), 1000)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startIso, active])

  return seconds
}
