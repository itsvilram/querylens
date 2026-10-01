import { VueQueryPlugin } from '@tanstack/vue-query'
import { render, screen } from '@testing-library/vue'
import { http, HttpResponse } from 'msw'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import App from '../App.vue'

import { server } from './msw'

function renderApp() {
  render(App, { global: { plugins: [createPinia(), VueQueryPlugin] } })
}

describe('App', () => {
  it('shows the app name as the main heading', () => {
    renderApp()

    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('QueryLens')
  })

  it('offers example questions', () => {
    renderApp()

    expect(
      screen.getByRole('button', { name: 'Which film categories made the most money in 2024?' }),
    ).toBeTruthy()
  })

  it('says when the server has no AI key (demo mode)', async () => {
    server.use(
      http.get('*/api/health', () =>
        HttpResponse.json({ status: 'ok', llm_mode: 'fake', demo: false }),
      ),
    )
    renderApp()

    expect(await screen.findByText(/Demo mode/)).toBeTruthy()
  })

  it('tells visitors of the public demo where their questions go', async () => {
    server.use(
      http.get('*/api/health', () =>
        HttpResponse.json({ status: 'ok', llm_mode: 'real', demo: true }),
      ),
    )
    renderApp()

    expect(
      await screen.findByText(/Public demo: your questions are sent to the AI provider/),
    ).toBeTruthy()
    expect(screen.getByText(/Don.t type private data/)).toBeTruthy()
  })

  it('has a skip link to the question box', () => {
    renderApp()

    expect(
      screen.getByRole('link', { name: 'Skip to the question box' }).getAttribute('href'),
    ).toBe('#question')
  })
})
