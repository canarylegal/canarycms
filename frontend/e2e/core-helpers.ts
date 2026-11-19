import { expect, type Page, type APIRequestContext } from '@playwright/test'

export function credentials(kind = 'STAFF') {
  const email = process.env[`E2E_${kind}_EMAIL`]
  const password = process.env[`E2E_${kind}_PASSWORD`]
  if (!email?.endsWith('@example.com') || !password || process.env.CANARY_TEST_FIXTURE !== '1') {
    throw new Error('Core tests require the dedicated disposable fixture and E2E credentials. See docs/CORE_WORKFLOWS.md.')
  }
  return { email, password }
}

export async function login(page: Page) {
  const user = credentials()
  await page.goto('/')
  await page.getByLabel('Email address', { exact: true }).fill(user.email)
  await page.getByLabel('Password', { exact: true }).fill(user.password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('button', { name: 'New matter', exact: true })).toBeVisible()
}

export async function apiLogin(request: APIRequestContext, kind: string) {
  const response = await request.post('/api/auth/login', { data: credentials(kind) })
  expect(response.status()).toBe(200)
}

export async function caseId(request: APIRequestContext, number = '900001') {
  const response = await request.get('/api/cases')
  expect(response.status()).toBe(200)
  const cases = await response.json() as { id: string; case_number: string; matter_description: string }[]
  const matter = cases.find((item) => item.case_number === number)
  if (!matter || !matter.matter_description.includes('CI ')) throw new Error('Synthetic matter fixture is missing')
  return matter.id
}
