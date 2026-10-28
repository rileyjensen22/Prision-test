/**
 * Dimmed night mode on a schedule. The window comes from the view when the API provides it
 * (`ui.night_mode`); until then these are the defaults. Pure and clock-injected so it is testable.
 */
export interface NightWindow {
  start: string // "HH:MM", 24 hour
  end: string
}

export const DEFAULT_NIGHT: NightWindow = { start: '21:00', end: '06:00' }

function minutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + (m || 0)
}

export function isNight(now: Date, window: NightWindow = DEFAULT_NIGHT): boolean {
  const cur = now.getHours() * 60 + now.getMinutes()
  const start = minutes(window.start)
  const end = minutes(window.end)
  if (start === end) return false
  return start < end ? cur >= start && cur < end : cur >= start || cur < end
}
