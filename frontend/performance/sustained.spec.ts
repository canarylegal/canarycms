import { expect, test, type APIRequestContext } from '@playwright/test'
import { performance } from 'node:perf_hooks'
import { writeFile } from 'node:fs/promises'
import { credentials } from '../e2e/core-helpers'

// Fixed-size histograms avoid retaining every response/timing during longer runs.
const bounds = [25, 50, 100, 250, 500, 1000, 2000, 3000, 5000, 10000, Infinity]
const histogram = () => bounds.map(() => 0)
const percentile = (counts: number[]) => {
  const target = Math.ceil(counts.reduce((a, b) => a + b, 0) * 0.95)
  let total = 0
  return bounds[counts.findIndex(n => (total += n) >= target)]
}

test('sustained mixed reads, writes and downloads remain healthy', async ({ playwright, baseURL }, info) => {
  if (process.env.CANARY_TEST_FIXTURE !== '1' || baseURL !== 'http://frontend') {
    throw new Error('Sustained load requires the isolated synthetic stack')
  }
  const seconds = Number(process.env.CANARY_SOAK_SECONDS ?? 300)
  if (!Number.isInteger(seconds) || seconds < 60 || seconds > 3600) throw new Error('CANARY_SOAK_SECONDS must be 60..3600')
  test.setTimeout((seconds + 90) * 1000)
  const contexts: APIRequestContext[] = []
  const metrics: Record<string, { count: number; early: number[]; late: number[]; all: number[]; max_ms: number }> = {}
  const cycles = [0, 0, 0, 0]
  let started = 0
  let finished = false
  try {
    for (let i = 0; i < 4; i++) {
      const ctx = await playwright.request.newContext({ baseURL, timeout: 10000 })
      contexts.push(ctx)
      const auth = await ctx.post('/api/auth/login', { data: { email: `performance-${i}@example.com`, password: credentials().password } })
      expect(auth.status()).toBe(200)
      await auth.dispose()
    }
    const lookup = await contexts[0].get('/api/cases?q=900001&limit=1')
    expect(lookup.status()).toBe(200)
    const cases = await lookup.json(); expect(cases).toHaveLength(1)
    await lookup.dispose()
    const id = cases[0].id
    const list = await contexts[0].get(`/api/cases/${id}/files`)
    expect(list.status()).toBe(200)
    const files = await list.json(); expect(files).toHaveLength(1200)
    await list.dispose()
    const file = files.find((f: { original_filename: string }) => f.original_filename === 'Performance document 0000.txt')
    expect(file).toBeTruthy()
    const downloadPath = `/api/cases/${id}/files/${file.id}`
    const original = await contexts[0].get(downloadPath)
    expect(original.status()).toBe(200)
    const expectedBytes = await original.body(); expect(expectedBytes.length).toBeGreaterThan(0)
    await original.dispose()
    started = performance.now()
    await Promise.all(contexts.map(async (ctx, index) => {
      while (performance.now() - started < seconds * 1000) {
        const direction = cycles[index] % 2 ? 'asc' : 'desc'
        const operations = [
          ['matters', '/api/cases/menu'],
          ['documents', `/api/cases/${id}/files/browse`],
          ['write', '/api/users/me/ui-preferences'],
          ['readback', '/api/auth/me'],
          ['download', downloadPath],
        ]
        for (const [name, path] of operations) {
          const begin = performance.now()
          const response = name === 'write'
            ? await ctx.put(path, { data: { main_menu_sort_dir: direction } })
            : await ctx.get(path)
          try {
            expect(response.status(), name).toBe(200)
            if (name === 'download') expect(await response.body()).toEqual(expectedBytes)
            else {
              const data = await response.json()
              if (name === 'matters' || name === 'documents') expect(data.items).toHaveLength(100)
              if (name === 'write' || name === 'readback') expect(data.ui_preferences.main_menu_sort_dir).toBe(direction)
            }
            const elapsed = performance.now() - begin
            const metric = metrics[name] ??= { count: 0, early: histogram(), late: histogram(), all: histogram(), max_ms: 0 }
            const bucket = bounds.findIndex(bound => elapsed <= bound)
            metric.count++; metric.all[bucket]++; metric.max_ms = Math.max(metric.max_ms, elapsed)
            const age = performance.now() - started
            if (age <= seconds * 1000 / 3) metric.early[bucket]++
            if (age >= seconds * 2000 / 3) metric.late[bucket]++
          } finally { await response.dispose() }
        }
        cycles[index]++
        await new Promise(resolve => setTimeout(resolve, 100))
      }
    }))
    expect(performance.now() - started).toBeGreaterThanOrEqual(seconds * 1000)
    for (const count of cycles) expect(count).toBeGreaterThanOrEqual(20)
    for (const metric of Object.values(metrics)) {
      expect(metric.early.reduce((a, b) => a + b, 0)).toBeGreaterThan(0)
      expect(metric.late.reduce((a, b) => a + b, 0)).toBeGreaterThan(0)
      expect(percentile(metric.all)).toBeLessThanOrEqual(3000)
      expect(percentile(metric.late)).toBeLessThanOrEqual(Math.max(1000, percentile(metric.early) * 3))
    }
    finished = true
  } finally {
    await Promise.all(contexts.map(ctx => ctx.dispose()))
    const report = { passed: finished, seconds, cycles, elapsed_ms: started ? performance.now() - started : 0,
      metrics: Object.fromEntries(Object.entries(metrics).map(([name, m]) => [name, { ...m, p95_ms_upper_bound: percentile(m.all), early_p95_ms_upper_bound: percentile(m.early), late_p95_ms_upper_bound: percentile(m.late) }])) }
    const body = JSON.stringify(report, null, 2)
    await info.attach('sustained-metrics.json', { body, contentType: 'application/json' })
    await writeFile(`${process.env.PLAYWRIGHT_OUTPUT_DIR ?? info.outputDir}/sustained-metrics.json`, body)
    console.log(JSON.stringify({ sustained_passed: finished, seconds, cycles }))
  }
})
