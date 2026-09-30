import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../App.vue'

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
}

describe('App', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        Promise.resolve(
          url.endsWith('/api/health')
            ? jsonResponse({ status: 'ok', llm_mode: 'fake' })
            : jsonResponse({ database: 'Pagila', tables: [] }),
        ),
      ),
    )
  })
  afterEach(() => vi.unstubAllGlobals())

  function mountApp() {
    return mount(App, { global: { plugins: [createPinia(), VueQueryPlugin] } })
  }

  it('shows the app name as the main heading', () => {
    expect(mountApp().get('h1').text()).toBe('QueryLens')
  })

  it('offers example questions and says when the server is in demo mode', async () => {
    const wrapper = mountApp()
    await flushPromises()

    expect(wrapper.text()).toContain('Which film categories made the most money in 2024?')
    expect(wrapper.text()).toContain('Demo mode')
  })
})
