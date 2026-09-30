import { defineStore } from 'pinia'
import { computed, markRaw, ref } from 'vue'

import type { Answer, ApiErrorBody, Stage } from '@/api/types'
import { newId } from '@/lib/ids'

export type TurnStatus = 'running' | 'done' | 'error' | 'cancelled'

export interface Turn {
  id: string
  question: string
  status: TurnStatus
  stages: Stage[] // in the order the server reported them
  answer: Answer | null
  error: ApiErrorBody | null
}

/**
 * The conversation on screen (client state). The server keeps its own short
 * history per session_id for follow-up questions; "New chat" starts a new id,
 * so the next question is understood on its own.
 */
export const useChatStore = defineStore('chat', () => {
  const sessionId = ref(newId())
  const turns = ref<Turn[]>([])
  const busy = computed(() => turns.value.some((turn) => turn.status === 'running'))

  function find(id: string): Turn | undefined {
    return turns.value.find((turn) => turn.id === id)
  }

  function start(question: string): string {
    const id = newId()
    turns.value.push({ id, question, status: 'running', stages: [], answer: null, error: null })
    return id
  }

  function addStage(id: string, stage: Stage) {
    const turn = find(id)
    if (turn?.status === 'running') turn.stages.push(stage)
  }

  function finish(id: string, answer: Answer) {
    const turn = find(id)
    if (turn?.status !== 'running') return
    // An answer never changes once it arrives: markRaw skips making its (up to
    // 1,000) rows deeply reactive.
    turn.answer = markRaw(answer)
    turn.status = 'done'
  }

  function fail(id: string, error: ApiErrorBody) {
    const turn = find(id)
    if (turn?.status !== 'running') return
    turn.error = error
    turn.status = 'error'
  }

  function cancel(id: string) {
    const turn = find(id)
    if (turn?.status === 'running') turn.status = 'cancelled'
  }

  function newChat() {
    sessionId.value = newId()
    turns.value = []
  }

  return { sessionId, turns, busy, find, start, addStage, finish, fail, cancel, newChat }
})
