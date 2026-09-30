import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import type { Answer } from '../api/types'
import { useChatStore } from '../stores/chat'

describe('chat store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('follows a turn from its stages to its answer', () => {
    const chat = useChatStore()
    const id = chat.start('How many films are there?')

    expect(chat.busy).toBe(true)
    chat.addStage(id, 'generate')
    chat.addStage(id, 'execute')
    chat.finish(id, { sql: 'SELECT 1' } as Answer)

    const turn = chat.find(id)!
    expect(turn.stages).toEqual(['generate', 'execute'])
    expect(turn.status).toBe('done')
    expect(chat.busy).toBe(false)
  })

  it('ignores late events for a turn that has already ended', () => {
    const chat = useChatStore()
    const id = chat.start('q')
    chat.fail(id, { code: 'llm_busy', message: 'busy' })

    chat.addStage(id, 'execute')
    chat.finish(id, { sql: 'SELECT 1' } as Answer)

    const turn = chat.find(id)!
    expect(turn.status).toBe('error')
    expect(turn.stages).toEqual([])
    expect(turn.answer).toBeNull()
  })

  it('starts a new chat with a new session id the API accepts', () => {
    const chat = useChatStore()
    const first = chat.sessionId
    chat.start('q')

    chat.newChat()

    expect(chat.turns).toEqual([])
    expect(chat.sessionId).not.toBe(first)
    expect(chat.sessionId).toMatch(/^[A-Za-z0-9-]{16,64}$/)
  })
})
