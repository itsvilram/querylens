import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { render, screen } from '@testing-library/vue'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'

import AskForm from '@/components/AskForm.vue'
import ChatTurn from '@/components/ChatTurn.vue'
import { askKey, useAskStream } from '@/composables/useAskStream'
import { useChatStore } from '@/stores/chat'
import { useModelStore } from '@/stores/model'

import { ANSWER, server, sse, streamed } from './msw'

const TWO_MODELS = {
  status: 'ok',
  llm_mode: 'real',
  demo: false,
  models: [
    { id: 'gemini', label: 'Gemini 3.5 Flash Lite' },
    { id: 'groq', label: 'GPT-OSS 120B (Groq)' },
  ],
  default_model: 'gemini',
}

function serverOffersTwoModels() {
  server.use(http.get('*/api/health', () => HttpResponse.json(TWO_MODELS)))
}

let pinia: Pinia

function renderWith(component: typeof AskForm | typeof ChatTurn, props: object = {}) {
  const stream = {
    ask: vi.fn<(question: string) => Promise<void>>(async () => {}),
    cancel: vi.fn<() => void>(),
  }
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(component, {
    props,
    global: {
      plugins: [pinia, [VueQueryPlugin, { queryClient }]],
      provide: { [askKey as symbol]: stream },
    },
  })
  return { ...stream, user: userEvent.setup() }
}

describe('model switch', () => {
  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
  })

  it('is offered when the server has more than one model, and remembers the pick', async () => {
    serverOffersTwoModels()
    const { user } = renderWith(AskForm)

    const select = await screen.findByLabelText('Model')
    expect(select).toHaveProperty('value', 'gemini') // the default
    await user.selectOptions(select, 'groq')

    expect(useModelStore().choice).toBe('groq')
    expect(localStorage.getItem('querylens-model')).toBe('groq')
  })

  it('names the provider the question goes to on the public demo', async () => {
    server.use(http.get('*/api/health', () => HttpResponse.json({ ...TWO_MODELS, demo: true })))
    const { user } = renderWith(AskForm)

    expect(await screen.findByText(/Questions go to Google \(Gemini\)/)).toBeTruthy()
    await user.selectOptions(screen.getByLabelText('Model'), 'groq')
    expect(screen.getByText(/Questions go to Groq/)).toBeTruthy()
  })

  it('is hidden when the server has only one model', async () => {
    renderWith(AskForm)
    await screen.findByLabelText('Your question')

    await vi.waitFor(() => expect(screen.queryByLabelText('Model')).toBeNull())
  })

  it('sends the picked model with the question', async () => {
    let sent: { model?: string } = {}
    server.use(
      http.post('*/api/ask/stream', async ({ request }) => {
        sent = (await request.json()) as { model?: string }
        return streamed([sse('answer', { ...ANSWER, model_id: 'groq' })])
      }),
    )
    useModelStore().choice = 'groq'
    const scope = effectScope()
    const { ask } = scope.run(() => useAskStream())!

    await ask('How many films are there?')

    expect(sent.model).toBe('groq')
    expect(useChatStore().turns[0]?.model).toBe('groq')
  })

  it('offers the other model when the daily quota is used up, and asks again with it', async () => {
    serverOffersTwoModels()
    const chat = useChatStore()
    const id = chat.start('How many films are there?', null)
    chat.fail(id, { code: 'daily_budget_used', message: "The AI's free daily quota is used up." })
    const { ask, user } = renderWith(ChatTurn, { turn: chat.turns[0] })

    await user.click(await screen.findByRole('button', { name: 'Try with GPT-OSS 120B (Groq)' }))

    expect(useModelStore().choice).toBe('groq')
    expect(ask).toHaveBeenCalledWith('How many films are there?')
  })

  it('does not offer another model for errors a model switch cannot fix', async () => {
    serverOffersTwoModels()
    const chat = useChatStore()
    const id = chat.start('Drop the films', null)
    chat.fail(id, { code: 'unsafe_sql', message: 'Blocked.' })
    renderWith(ChatTurn, { turn: chat.turns[0] })

    await screen.findByRole('button', { name: 'Try again' })
    expect(screen.queryByRole('button', { name: /Try with/ })).toBeNull()
  })
})
