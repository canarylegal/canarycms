import { defineConfig, devices } from '@playwright/test'

/**
 * Thin browser smoke — staff login shell + portal sign-in page.
 * Requires a running stack (frontend + backend). See docs/TESTING.md.
 *
 *   BASE_URL=http://127.0.0.1:8080 \
 *   E2E_STAFF_EMAIL=… E2E_STAFF_PASSWORD=… \
 *   npm run test:e2e
 */
const baseURL = process.env.BASE_URL?.trim() || 'http://127.0.0.1:8080'

export default defineConfig({
  testDir: './e2e',
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR || 'test-results',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  use: {
    ...devices['Desktop Chrome'],
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
