import { http, HttpResponse } from 'msw'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { effectScope } from 'vue'

import { useAskStream } from '@/composables/useAskStream'
import { useChatStore } from '@/stores/chat'

import { ANSWER, server, sse, streamed } from './msw'

function setup() {
  const scope = effectScope()
  const stream = scope.run(() => useAskStream())!
  return { ...stream, chat: useChatStore(), scope }
}

describe('useAskStream', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('follows the stages and stores the answer', async () => {
    let sent: unknown
    server.use(
      http.post('*/api/ask/stream', async ({ request }) => {
        sent = await request.json()
        return streamed([
          sse('stage', { stage: 'generate' }),
          ': ping\n\n',
          sse('stage', { stage: 'execute' }),
          sse('answer', ANSWER),
        ])
      }),
    )
    const { ask, chat } = setup()

    await ask('  How many films are there?  ')

    const turn = chat.turns[0]!
    expect(turn.status).toBe('done')
    expect(turn.stages).toEqual(['generate', 'execute'])
    expect(turn.answer?.rows).toEqual([[1000]])
    expect(sent).toEqual({ question: 'How many films are there?', session_id: chat.sessionId })
  })

  it('turns a refusal before the stream (429) into a rate-limited error', async () => {
    server.use(
      http.post('*/api/ask/stream', () =>
        HttpResponse.json(
          { error: { code: 'rate_limited', message: 'Too many questions.', request_id: 'r1' } },
          { status: 429, headers: { 'Retry-After': '42' } },
        ),
      ),
    )
    const { ask, chat } = setup()

    await ask('q')

    expect(chat.turns[0]?.error).toEqual({
      code: 'rate_limited',
      message: 'Too many questions.',
      request_id: 'r1',
      retry_after_s: 42,
    })
  })

  it('shows an error event from the stream', async () => {
    const error = { code: 'unsafe_sql', message: 'Blocked.', request_id: 'r2' }
    server.use(
      http.post('*/api/ask/stream', () =>
        streamed([sse('stage', { stage: 'generate' }), sse('error', error)]),
      ),
    )
    const { ask, chat } = setup()

    await ask('Drop the films')

    expect(chat.turns[0]?.status).toBe('error')
    expect(chat.turns[0]?.error).toEqual(error)
  })

  it('reports a stream that ends without an answer', async () => {
    server.use(http.post('*/api/ask/stream', () => streamed([sse('stage', { stage: 'generate' })])))
    const { ask, chat } = setup()

    await ask('q')

    expect(chat.turns[0]?.error?.code).toBe('connection_lost')
  })

  it('reports a server it cannot reach', async () => {
    server.use(http.post('*/api/ask/stream', () => HttpResponse.error()))
    const { ask, chat } = setup()

    await ask('q')

    expect(chat.turns[0]?.error?.code).toBe('network_error')
  })

  it('stops a question when asked to', async () => {
    server.use(
      http.post('*/api/ask/stream', () =>
        streamed([sse('stage', { stage: 'generate' })], { open: true }),
      ),
    )
    const { ask, cancel, chat } = setup()

    const asking = ask('q')
    await expect.poll(() => chat.turns[0]?.stages.length).toBe(1)
    cancel()
    await asking

    expect(chat.turns[0]?.status).toBe('cancelled')
    expect(chat.busy).toBe(false)
  })

  it('ignores empty questions and questions sent while one is running', async () => {
    server.use(
      http.post('*/api/ask/stream', () =>
        streamed([sse('stage', { stage: 'generate' })], { open: true }),
      ),
    )
    const { ask, cancel, chat } = setup()

    await ask('   ')
    const first = ask('first')
    await ask('second')

    expect(chat.turns.map((t) => t.question)).toEqual(['first'])
    cancel()
    await first
  })
})
