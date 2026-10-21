import { enqueue, flushQueue, loadQueue } from './queue'
import type { QueuedEvent } from './queue'

function memory() {
  const m = new Map<string, string>()
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, v),
  }
}
const ev = (id: string): QueuedEvent => ({
  type: 'request',
  client_id: id,
  payload: { kind: 'staff', created_at: 'x' },
})

test('events persist and flush in order', async () => {
  const s = memory()
  enqueue(ev('a'), s)
  enqueue(ev('b'), s)
  expect(loadQueue(s)).toHaveLength(2)
  const sent: string[] = []
  const left = await flushQueue(async (e) => (sent.push(e.client_id), true), s)
  expect(sent).toEqual(['a', 'b'])
  expect(left).toEqual([])
  expect(loadQueue(s)).toEqual([])
})

test('stops at the first failure and keeps the rest', async () => {
  const s = memory()
  ;['a', 'b', 'c'].forEach((id) => enqueue(ev(id), s))
  let n = 0
  const left = await flushQueue(async () => {
    if (++n === 2) throw new Error('offline')
    return true
  }, s)
  expect(left.map((e) => e.client_id)).toEqual(['b', 'c'])
  expect(loadQueue(s).map((e) => e.client_id)).toEqual(['b', 'c'])
})
