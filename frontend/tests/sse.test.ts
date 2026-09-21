import { describe, expect, it, vi } from 'vitest'
import { connectSse, createSseParser } from '../app/utils/sse'
import type { SseStatus } from '../app/utils/sse'

describe('createSseParser', () => {
  it('parses events split across chunks', () => {
    const p = createSseParser()
    expect(p.push('event: order.created\nda')).toEqual([])
    expect(p.push('ta: {"order_id":1}\n\nevent: ready\ndata: {}\n\n')).toEqual([
      { event: 'order.created', data: '{"order_id":1}', id: undefined },
      { event: 'ready', data: '{}', id: undefined },
    ])
  })

  it('ignores heartbeats/comments, handles CRLF, multi-line data and default event name', () => {
    const p = createSseParser()
    expect(p.push(': ping\n\n')).toEqual([])
    expect(p.push('data: one\r\ndata: two\r\n\r\n')).toEqual([{ event: 'message', data: 'one\ntwo', id: undefined }])
    expect(p.push('retry: 3000\n\nid: 7\nevent: x\ndata: y\n\n')).toEqual([{ event: 'x', data: 'y', id: '7' }])
  })
})

// --- a fake fetch whose body we control ----------------------------------------------------------

const enc = new TextEncoder()

function streamResponse(chunks: string[], opts: { hang?: boolean, signal?: AbortSignal } = {}) {
  let i = 0
  return {
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: () => {
          if (i < chunks.length) return Promise.resolve({ done: false, value: enc.encode(chunks[i++]) })
          if (!opts.hang) return Promise.resolve({ done: true, value: undefined })
          return new Promise((_, reject) => opts.signal?.addEventListener('abort', () => reject(new Error('aborted'))))
        },
      }),
    },
  } as unknown as Response
}

const status = (code: number) => ({ ok: false, status: code, body: null }) as unknown as Response
const tick = (ms = 10) => new Promise(r => setTimeout(r, ms))
const FAST = { minDelayMs: 5, maxDelayMs: 20 }

describe('connectSse', () => {
  it('reports live on ready, forwards parsed events and sends the bearer token', async () => {
    const seen: [string, unknown][] = []
    const statuses: SseStatus[] = []
    const fetchImpl = vi.fn().mockImplementation((_url: string, init: RequestInit) =>
      Promise.resolve(streamResponse(['event: ready\ndata: {"type":"ready"}\n\n', 'event: order.status\ndata: {"order_id":3,"status":"READY"}\n\n'], { hang: true, signal: init.signal as AbortSignal })))

    const conn = connectSse({ url: 'http://api/stream', getToken: () => 'tok', fetchImpl, ...FAST,
      onEvent: (t, d) => seen.push([t, d]), onStatus: s => statuses.push(s) })
    await tick(30)
    conn.close()

    expect(fetchImpl.mock.calls[0]![1].headers).toMatchObject({ Authorization: 'Bearer tok', Accept: 'text/event-stream' })
    expect(seen).toEqual([['ready', { type: 'ready' }], ['order.status', { order_id: 3, status: 'READY' }]])
    expect(statuses.slice(0, 2)).toEqual(['connecting', 'live'])
    await tick(10)
    expect(statuses.at(-1)).toBe('closed')
  })

  it('reconnects with backoff when the stream ends, and fires ready again', async () => {
    let calls = 0
    const readies = vi.fn()
    const fetchImpl = vi.fn().mockImplementation(async () => {
      calls++
      return streamResponse(['event: ready\ndata: {}\n\n'])       // ends immediately -> reconnect
    })
    const conn = connectSse({ url: 'u', getToken: () => 't', fetchImpl, ...FAST, onEvent: t => t === 'ready' && readies() })
    await tick(120)
    conn.close()
    expect(calls).toBeGreaterThanOrEqual(3)
    expect(readies.mock.calls.length).toBe(calls - (calls > readies.mock.calls.length ? 1 : 0) || calls)
  })

  it('retries after network errors', async () => {
    let calls = 0
    const fetchImpl = vi.fn().mockImplementation(async () => {
      calls++
      if (calls < 3) throw new TypeError('offline')
      return streamResponse(['event: ready\ndata: {}\n\n'], { hang: true })
    })
    const statuses: SseStatus[] = []
    const conn = connectSse({ url: 'u', getToken: () => 't', fetchImpl, ...FAST, onEvent: () => {}, onStatus: s => statuses.push(s) })
    await tick(150)
    conn.close()
    expect(calls).toBe(3)
    expect(statuses).toContain('live')
  })

  it('renews an expired session once and retries immediately with the new token', async () => {
    let token = 'expired'
    const auth: (string | undefined)[] = []
    const fetchImpl = vi.fn().mockImplementation(async (_u: string, init: RequestInit) => {
      const h = (init.headers as Record<string, string>).Authorization
      auth.push(h)
      return h === 'Bearer fresh' ? streamResponse(['event: ready\ndata: {}\n\n'], { hang: true, signal: init.signal as AbortSignal }) : status(401)
    })
    const onAuthExpired = vi.fn().mockImplementation(async () => { token = 'fresh'; return true })
    const conn = connectSse({ url: 'u', getToken: () => token, fetchImpl, onAuthExpired, ...FAST, onEvent: () => {} })
    await tick(40)
    conn.close()
    expect(auth.slice(0, 2)).toEqual(['Bearer expired', 'Bearer fresh'])
    expect(onAuthExpired).toHaveBeenCalledTimes(1)
  })

  it('gives up (closed) when the session cannot be renewed, without hammering the server', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(status(401))
    const statuses: SseStatus[] = []
    connectSse({ url: 'u', getToken: () => 'x', fetchImpl, onAuthExpired: async () => false, ...FAST, onEvent: () => {}, onStatus: s => statuses.push(s) })
    await tick(60)
    expect(fetchImpl).toHaveBeenCalledTimes(1)
    expect(statuses.at(-1)).toBe('closed')
  })

  it('does not retry on 403/404 (not allowed / wrong restaurant)', async () => {
    for (const code of [403, 404]) {
      const fetchImpl = vi.fn().mockResolvedValue(status(code))
      connectSse({ url: 'u', getToken: () => 'x', fetchImpl, ...FAST, onEvent: () => {} })
      await tick(40)
      expect(fetchImpl).toHaveBeenCalledTimes(1)
    }
  })

  it('detects a silently dead connection (no data, no close) and reconnects', async () => {
    let calls = 0
    const fetchImpl = vi.fn().mockImplementation(async (_u: string, init: RequestInit) => {
      calls++
      return streamResponse(['event: ready\ndata: {}\n\n'], { hang: true, signal: init.signal as AbortSignal })   // then goes silent
    })
    const conn = connectSse({ url: 'u', getToken: () => 't', fetchImpl, ...FAST, staleAfterMs: 60, onEvent: () => {} })
    await tick(400)
    conn.close()
    expect(calls).toBeGreaterThanOrEqual(2)
  })

  it('close() stops all further attempts', async () => {
    const fetchImpl = vi.fn().mockImplementation(async () => streamResponse(['event: ready\ndata: {}\n\n']))
    const conn = connectSse({ url: 'u', getToken: () => 't', fetchImpl, ...FAST, onEvent: () => {} })
    await tick(30)
    conn.close()
    const seen = fetchImpl.mock.calls.length
    await tick(100)
    expect(fetchImpl.mock.calls.length).toBe(seen)
  })
})
