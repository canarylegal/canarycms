import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  testDir: './performance', workers: 1, retries: 0, timeout: 120_000,
  expect: { timeout: 30_000 }, reporter: [['list']],
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR || 'test-results/performance',
  use: { ...devices['Desktop Chrome'], baseURL: process.env.BASE_URL || 'http://frontend',
    trace: 'retain-on-failure', screenshot: 'only-on-failure' },
})
