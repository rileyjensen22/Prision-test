/**
 * Health numbers the kiosk reports about itself. Nothing here reads a camera or microphone: it only
 * asks the browser whether such devices exist. No pictures, audio or resident data are sent.
 */
import { NetworkError, HttpError } from './api'

export type Presence = 'ok' | 'missing' | 'blocked' | 'unknown'

export interface Health {
  storage_used_mb: number
  storage_quota_mb: number
  camera: Presence
  microphone: Presence
  app_version: string
  queue_pending: number
  online: boolean
}

export interface NavLike {
  onLine?: boolean
  storage?: { estimate?: () => Promise<{ usage?: number; quota?: number }> }
  mediaDevices?: { enumerateDevices?: () => Promise<{ kind: string }[]> }
}

const MB = 1024 * 1024

export async function collectHealth(
  nav: NavLike,
  pending: number,
  version = 'dev',
): Promise<Health> {
  let used = 0
  let quota = 0
  try {
    const est = await nav.storage?.estimate?.()
    used = Math.round((est?.usage ?? 0) / MB)
    quota = Math.round((est?.quota ?? 0) / MB)
  } catch {
    // leave zeros: "unknown" is better than failing the report
  }
  let camera: Presence = 'unknown'
  let microphone: Presence = 'unknown'
  try {
    const list = await nav.mediaDevices?.enumerateDevices?.()
    if (list) {
      camera = list.some((d) => d.kind === 'videoinput') ? 'ok' : 'missing'
      microphone = list.some((d) => d.kind === 'audioinput') ? 'ok' : 'missing'
    }
  } catch {
    // keep unknown
  }
  return {
    storage_used_mb: used,
    storage_quota_mb: quota,
    camera,
    microphone,
    app_version: version.slice(0, 32),
    queue_pending: Math.max(0, pending),
    online: nav.onLine !== false,
  }
}

export interface Command {
  id: number
  kind: string
}

export async function sendHeartbeat(
  token: string,
  health: Health,
  ack: number[] = [],
): Promise<Command[]> {
  let res: Response
  try {
    res = await fetch('/api/device/heartbeat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Device-Token': token },
      body: JSON.stringify({ ...health, ack }),
    })
  } catch {
    throw new NetworkError('offline')
  }
  if (!res.ok) throw new HttpError(res.status, null)
  return ((await res.json()) as { commands: Command[] }).commands
}

/** Runs a heartbeat, acknowledges restart commands, and reloads the app when asked to. */
export async function beat(
  token: string,
  nav: NavLike,
  pending: number,
  reload: () => void,
  version?: string,
): Promise<void> {
  const health = await collectHealth(nav, pending, version)
  const commands = await sendHeartbeat(token, health)
  const restarts = commands.filter((c) => c.kind === 'restart').map((c) => c.id)
  if (restarts.length) {
    await sendHeartbeat(token, health, restarts) // tell the server before we go away
    reload()
  }
}
