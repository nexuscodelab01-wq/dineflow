/**
 * Minimal Server-Sent Events client built on fetch().
 *
 * Why not the browser's EventSource? It can't send an Authorization header, and putting a token in
 * the URL leaks it into logs. fetch() streams work with normal headers, so the same bearer token
 * (and silent refresh) used everywhere else applies here.
 *
 * Framework-free so it can be unit tested.
 */

export type SseStatus = 'connecting' | 'live' | 'reconnecting' | 'closed'

export type SseMessage = { event: string, data: string, id?: string }

/** Incremental parser for the text/event-stream format. */
export function createSseParser() {
  let buffer = ''
  return {
    push(chunk: string): SseMessage[] {
      buffer += chunk.replace(/\r\n?/g, '\n')
      const messages: SseMessage[] = []
      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        const block = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const message = parseBlock(block)
        if (message) messages.push(message)
        boundary = buffer.indexOf('\n\n')
      }
      return messages
    },
  }
}

function parseBlock(block: string): SseMessage | null {
  let event = 'message'
  let id: string | undefined
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (!line || line.startsWith(':')) continue // comment / heartbeat
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    const value = colon === -1 ? '' : line.slice(colon + 1).replace(/^ /, '')
    if (field === 'event') event = value
    else if (field === 'data') data.push(value)
    else if (field === 'id') id = value
  }
  return data.length ? { event, data: data.join('\n'), id } : null
}

export type SseOptions = {
  url: string
  getToken: () => string | null
  /** Called for every event; `data` is the parsed JSON payload (or the raw string). */
  onEvent: (type: string, data: unknown) => void
  onStatus?: (status: SseStatus) => void
  /** Try to renew the session after a 401; resolve true if a new token is available. */
  onAuthExpired?: () => Promise<boolean>
  fetchImpl?: typeof fetch
  minDelayMs?: number
  maxDelayMs?: number
  /** No bytes for this long (the server pings every 15 s) means the connection silently died. */
  staleAfterMs?: number
}

export function connectSse(options: SseOptions): { close: () => void } {
  const {
    fetchImpl = (...args: Parameters<typeof fetch>) => fetch(...args),
    minDelayMs = 1000,
    maxDelayMs = 30000,
    staleAfterMs = 45000,
  } = options
  let closed = false
  let controller: AbortController | null = null
  let wakeUp: (() => void) | null = null

  const setStatus = (s: SseStatus) => options.onStatus?.(s)
  const sleep = (ms: number) => new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, ms)
    wakeUp = () => {
      clearTimeout(timer)
      resolve()
    }
  })

  async function run() {
    let delay = minDelayMs
    let renewedAuth = false
    let first = true

    while (!closed) {
      setStatus(first ? 'connecting' : 'reconnecting')
      first = false
      controller = new AbortController()
      let lastActivity = Date.now()
      const watchdog = setInterval(() => {
        if (Date.now() - lastActivity > staleAfterMs) controller?.abort()
      }, Math.max(50, Math.min(5000, staleAfterMs / 3)))

      try {
        const token = options.getToken()
        const response = await fetchImpl(options.url, {
          headers: { Accept: 'text/event-stream', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          signal: controller.signal,
        })

        if (response.status === 401) {
          if (!renewedAuth && options.onAuthExpired && await options.onAuthExpired()) {
            renewedAuth = true
            continue // retry immediately with the new token
          }
          break // signed out
        }
        if (response.status === 403 || response.status === 404) break // permanent: no point retrying
        if (!response.ok || !response.body) throw new Error(`Stream failed (${response.status})`)

        renewedAuth = false
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        const parser = createSseParser()
        for (;;) {
          const { done, value } = await reader.read()
          if (done) break
          lastActivity = Date.now()
          for (const message of parser.push(decoder.decode(value, { stream: true }))) {
            if (message.event === 'ready') {
              delay = minDelayMs // healthy connection: reset the backoff
              setStatus('live')
            }
            let payload: unknown = message.data
            try {
              payload = JSON.parse(message.data)
            }
            catch { /* keep the raw string */ }
            options.onEvent(message.event, payload)
          }
        }
      }
      catch {
        // aborted (close() or watchdog) or a network error: fall through to reconnect
      }
      finally {
        clearInterval(watchdog)
      }

      if (closed) break
      setStatus('reconnecting')
      await sleep(delay * (0.75 + Math.random() * 0.5)) // jitter, so a server restart isn't stampeded
      delay = Math.min(delay * 2, maxDelayMs)
    }
    setStatus('closed')
  }

  void run()

  return {
    close() {
      closed = true
      controller?.abort()
      wakeUp?.()
    },
  }
}
