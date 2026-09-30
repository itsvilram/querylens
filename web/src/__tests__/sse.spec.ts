import { describe, expect, it } from 'vitest'

import { parseEvent, readSse, type SseEvent } from '../api/sse'

/** A response body that arrives in these exact chunks, like a slow network. */
function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
}

async function collect(chunks: string[]): Promise<SseEvent[]> {
  const events: SseEvent[] = []
  for await (const event of readSse(streamOf(chunks))) events.push(event)
  return events
}

const STAGE = 'event: stage\ndata: {"stage":"generate"}\n\n'
const ANSWER = 'event: answer\ndata: {"sql":"SELECT 1"}\n\n'

describe('readSse', () => {
  it('reads named events in order', async () => {
    expect(await collect([STAGE + ANSWER])).toEqual([
      { event: 'stage', data: '{"stage":"generate"}' },
      { event: 'answer', data: '{"sql":"SELECT 1"}' },
    ])
  })

  it('joins events split anywhere across chunks', async () => {
    const text = STAGE + ANSWER
    for (let cut = 1; cut < text.length; cut++) {
      const events = await collect([text.slice(0, cut), text.slice(cut)])
      expect(events.map((e) => e.event)).toEqual(['stage', 'answer'])
    }
  })

  it('keeps a character that was split between chunks', async () => {
    const bytes = new TextEncoder().encode('data: café\n\n')
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, 10)) // "é" is two bytes: cut between them
        controller.enqueue(bytes.slice(10))
        controller.close()
      },
    })
    const events: SseEvent[] = []
    for await (const event of readSse(body)) events.push(event)
    expect(events).toEqual([{ event: 'message', data: 'café' }])
  })

  it('skips keep-alive comments and accepts CRLF line endings', async () => {
    const events = await collect([': ping\r\n\r\n', STAGE.replaceAll('\n', '\r\n')])
    expect(events).toEqual([{ event: 'stage', data: '{"stage":"generate"}' }])
  })

  it('reads a last event that has no closing blank line', async () => {
    expect(await collect(['event: answer\ndata: {}'])).toEqual([{ event: 'answer', data: '{}' }])
  })
})

describe('parseEvent', () => {
  it('joins multi-line data with newlines', () => {
    expect(parseEvent('data: a\ndata: b')).toEqual({ event: 'message', data: 'a\nb' })
  })

  it('returns null for a block with no data', () => {
    expect(parseEvent(': just a comment')).toBeNull()
  })
})
