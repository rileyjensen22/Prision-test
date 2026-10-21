import { useEffect } from 'react'

/** Calls onIdle after `seconds` without any touch, pointer or key input. */
export function useInactivity(seconds: number, onIdle: () => void) {
  useEffect(() => {
    let timer = setTimeout(onIdle, seconds * 1000)
    const reset = () => {
      clearTimeout(timer)
      timer = setTimeout(onIdle, seconds * 1000)
    }
    const events = ['pointerdown', 'keydown', 'touchstart'] as const
    events.forEach((e) => window.addEventListener(e, reset))
    return () => {
      clearTimeout(timer)
      events.forEach((e) => window.removeEventListener(e, reset))
    }
  }, [seconds, onIdle])
}
