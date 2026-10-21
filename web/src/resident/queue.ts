/** Offline event queue (CLAUDE.md section 7). Entries replay when the device is back online. */
export type QueuedEvent =
  | { type: 'request'; client_id: string; payload: { kind: string; created_at: string } }
  | { type: 'appeal'; client_id: string; payload: { sanction_id: number } }

const KEY = 'isd.queue'

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>

export function loadQueue(storage: StorageLike = localStorage): QueuedEvent[] {
  try {
    return JSON.parse(storage.getItem(KEY) ?? '[]') as QueuedEvent[]
  } catch {
    return []
  }
}

function save(q: QueuedEvent[], storage: StorageLike) {
  storage.setItem(KEY, JSON.stringify(q))
}

export function enqueue(ev: QueuedEvent, storage: StorageLike = localStorage): QueuedEvent[] {
  const q = [...loadQueue(storage), ev]
  save(q, storage)
  return q
}

/** Sends queued events in order. `send` returns true when delivered (or already delivered). */
export async function flushQueue(
  send: (ev: QueuedEvent) => Promise<boolean>,
  storage: StorageLike = localStorage,
): Promise<QueuedEvent[]> {
  let q = loadQueue(storage)
  while (q.length) {
    let delivered: boolean
    try {
      delivered = await send(q[0])
    } catch {
      break // still offline: keep the rest for next time
    }
    if (!delivered) break
    q = q.slice(1)
    save(q, storage)
  }
  return q
}

export function newClientId(): string {
  return crypto.randomUUID()
}
