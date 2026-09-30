// Runs before every test file (vitest.config.ts: setupFiles).
import { cleanup } from '@testing-library/vue'
import { afterAll, afterEach, beforeAll } from 'vitest'

import { server } from './msw'

// Any request without a handler fails the test: no silent real network calls.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers() // drop handlers a test added with server.use()
  cleanup() // unmount what Testing Library rendered
})
afterAll(() => server.close())
