/**
 * Read server-sent events from a fetch() response body.
 *
 * The browser's EventSource can only send GET requests, and /api/ask/stream is
 * a POST with a JSON body, so we read the stream ourselves. The format is
 * simple text: events are separated by a blank line, each line is
 * "field: value", and lines starting with ":" are comments (keep-alive pings).
 * A network chunk can end anywhere, even mid-line, so text is buffered until
 * an event is complete.
 */

export interface SseEvent {
  event: string // "message" when the server named none
  data: string
}

export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseEvent> {
  const reader = body.getReader()
  const decoder = new TextDecoder() // stream mode: a UTF-8 character split across chunks is kept
  let buffer = ''
  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      // Drop \r so "\r\n" line endings work too (safe even if a chunk ends between \r and \n).
      buffer += decoder.decode(value, { stream: true }).replaceAll('\r', '')
      let end = buffer.indexOf('\n\n')
      while (end !== -1) {
        const event = parseEvent(buffer.slice(0, end))
        buffer = buffer.slice(end + 2)
        if (event) yield event
        end = buffer.indexOf('\n\n')
      }
    }
    const last = parseEvent(buffer + decoder.decode().replaceAll('\r', ''))
    if (last) yield last // the stream ended without a final blank line
  } finally {
    reader.releaseLock()
  }
}

/** One event block (the lines between blank lines), or null for a comment-only block. */
export function parseEvent(block: string): SseEvent | null {
  let event = 'message'
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line === '' || line.startsWith(':')) continue
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    const value = colon === -1 ? '' : line.slice(colon + 1).replace(/^ /, '')
    if (field === 'event') event = value
    else if (field === 'data') data.push(value)
  }
  return data.length ? { event, data: data.join('\n') } : null
}
