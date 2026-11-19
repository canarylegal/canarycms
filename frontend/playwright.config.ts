import { defineConfig, devices } from '@playwright/test'

/** Core workflows use an isolated seeded stack: make test-core-workflows.
 * See docs/CORE_WORKFLOWS.md. Never point the fixture suite at deployment data.
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
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
