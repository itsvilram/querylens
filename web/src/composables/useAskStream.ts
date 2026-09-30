import { inject, onScopeDispose, type InjectionKey } from 'vue'

import { toApiError } from '@/api/client'
import { readSse } from '@/api/sse'
import type { Answer, ApiErrorBody, Stage } from '@/api/types'
import { useChatStore } from '@/stores/chat'

const CONNECTION_LOST: ApiErrorBody = {
  code: 'connection_lost',
  message: 'The connection closed before the answer arrived. Please try again.',
}
const NETWORK_ERROR: ApiErrorBody = {
  code: 'network_error',
  message: 'Could not reach the server. Check your connection and try again.',
}

/**
 * Ask a question and follow its progress live.
 *
 * POSTs to /api/ask/stream and reads the server-sent events with fetch() (see
 * api/sse.ts): each "stage" event moves the progress on, then one "answer" or
 * "error" event ends the turn. Everything lands in the chat store, so any
 * component can show it. A request that is refused before the stream starts
 * (e.g. 429, rate limited) comes back as a normal HTTP error.
 */
export function useAskStream() {
  const chat = useChatStore()
  let controller: AbortController | null = null

  async function ask(question: string): Promise<void> {
    const text = question.trim()
    if (!text || chat.busy) return
    const id = chat.start(text)
    controller = new AbortController()
    try {
      const response = await fetch('/api/ask/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify({ question: text, session_id: chat.sessionId }),
        signal: controller.signal,
      })
      if (!response.ok || !response.body) {
        chat.fail(id, (await toApiError(response)).body)
        return
      }
      for await (const { event, data } of readSse(response.body)) {
        if (event === 'stage') chat.addStage(id, (JSON.parse(data) as { stage: Stage }).stage)
        else if (event === 'answer') chat.finish(id, JSON.parse(data) as Answer)
        else if (event === 'error') chat.fail(id, JSON.parse(data) as ApiErrorBody)
      }
      chat.fail(id, CONNECTION_LOST) // does nothing if the turn already ended
    } catch {
      if (controller.signal.aborted) chat.cancel(id)
      else chat.fail(id, NETWORK_ERROR)
    } finally {
      controller = null
    }
  }

  /** Stop the current question (the server stops working on it too). */
  function cancel() {
    controller?.abort()
  }

  onScopeDispose(cancel)
  return { ask, cancel }
}

export type AskStream = ReturnType<typeof useAskStream>

/** App.vue creates the one AskStream and provides it; components ask through it. */
export const askKey: InjectionKey<AskStream> = Symbol('ask')

export function useAsk(): AskStream {
  const stream = inject(askKey)
  if (!stream) throw new Error('useAsk() needs App.vue to provide askKey')
  return stream
}
