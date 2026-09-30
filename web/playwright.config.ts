import process from 'node:process'
import { defineConfig, devices } from '@playwright/test'

// End-to-end tests: the real FastAPI app (fake LLM, so no key and no network),
// real Postgres and Redis (`docker compose up -d db redis`), and the production
// build of the web app. Both servers use their own ports, so a dev server that
// is already running (with other settings) is never reused by mistake.
const API_PORT = 8010
const WEB_PORT = 4174

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  forbidOnly: !!process.env.CI, // fail CI if a `test.only` was left behind
  retries: process.env.CI ? 2 : 0,
  workers: 1, // one API server and one Redis: run the tests one after another
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      // CI installs Playwright's Chromium; on a Windows dev machine the installed Edge is used.
      use: { ...devices['Desktop Chrome'], channel: process.env.CI ? undefined : 'msedge' },
    },
  ],
  webServer: [
    {
      command: `uv run uvicorn app.main:app --port ${API_PORT}`,
      cwd: '../api',
      url: `http://127.0.0.1:${API_PORT}/api/health`,
      reuseExistingServer: false,
      env: {
        LLM_MODE: 'fake',
        REDIS_URL: 'redis://127.0.0.1:6379/13', // not the app's 0 or the API tests' 15
        RATE_LIMIT_PER_MINUTE: '3', // low, so the rate-limit test is quick
        RATE_LIMIT_PER_HOUR: '1000',
        // The preview server proxies /api from this machine; trust its
        // X-Forwarded-For, so each test can act as its own client (e2e/app.spec.ts).
        TRUSTED_PROXIES: '["127.0.0.1/32", "::1/128"]',
      },
    },
    {
      command: `npm run build-only && npx vite preview --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: false,
      env: { API_URL: `http://127.0.0.1:${API_PORT}` },
    },
  ],
})
