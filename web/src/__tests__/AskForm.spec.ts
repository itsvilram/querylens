import { VueQueryPlugin } from '@tanstack/vue-query'
import { render, screen } from '@testing-library/vue'
import userEvent from '@testing-library/user-event'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AskForm from '@/components/AskForm.vue'
import { askKey } from '@/composables/useAskStream'
import { useChatStore } from '@/stores/chat'

function renderForm() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const stream = {
    ask: vi.fn<(question: string) => Promise<void>>(async () => {}),
    cancel: vi.fn<() => void>(),
  }
  render(AskForm, {
    global: { plugins: [pinia, VueQueryPlugin], provide: { [askKey as symbol]: stream } },
  })
  return { ...stream, user: userEvent.setup(), box: screen.getByLabelText('Your question') }
}

describe('AskForm', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('sends the question with Enter and clears the box', async () => {
    const { ask, user, box } = renderForm()

    await user.type(box, 'How many films are there?{Enter}')

    expect(ask).toHaveBeenCalledWith('How many films are there?')
    expect(box).toHaveProperty('value', '')
  })

  it('adds a new line with Shift+Enter instead of sending', async () => {
    const { ask, user, box } = renderForm()

    await user.type(box, 'line one{Shift>}{Enter}{/Shift}line two')

    expect(ask).not.toHaveBeenCalled()
    expect(box).toHaveProperty('value', 'line one\nline two')
  })

  it('can only send a question that has text', async () => {
    const { user, box } = renderForm()
    const button = screen.getByRole('button', { name: 'Ask' })

    expect(button).toHaveProperty('disabled', true)
    await user.type(box, '   ')
    expect(button).toHaveProperty('disabled', true)
    await user.type(box, 'films?')
    expect(button).toHaveProperty('disabled', false)
  })

  it('offers Stop while a question is running, and does not send another', async () => {
    const { ask, cancel, user, box } = renderForm()
    useChatStore().start('running question')

    await user.type(box, 'next question{Enter}')
    await user.click(await screen.findByRole('button', { name: 'Stop' }))

    expect(ask).not.toHaveBeenCalled()
    expect(cancel).toHaveBeenCalledOnce()
    expect(box).toHaveProperty('value', 'next question') // kept for later
  })

  it('shows how many of the 500 characters are used', async () => {
    const { user, box } = renderForm()

    await user.type(box, 'abc')

    expect(screen.getByText('3/500')).toBeTruthy()
    expect(box.getAttribute('maxlength')).toBe('500')
  })
})
