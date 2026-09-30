import process from 'node:process'
import { defineConfig, devices } from '@playwright/test'

// End-to-end tests. Phase 10 adds the real ones, run against LLM_MODE=fake.
// Docs: https://playwright.dev/docs/test-configuration
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  forbidOnly: !!process.env.CI, // fail CI if a `test.only` was left behind
  retries: process.env.CI ? 2 : 0,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:4173',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    // Test the production build, served by `vite preview`.
    command: 'npm run build-only && npm run preview',
    port: 4173,
    reuseExistingServer: !process.env.CI,
  },
})
