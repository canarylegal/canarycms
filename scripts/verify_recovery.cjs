// Run in the pinned Playwright image attached ONLY to the recovery network.
const { chromium, expect } = require('/app/node_modules/@playwright/test');
const fs = require('fs');
const crypto = require('crypto');
const { execFileSync } = require('child_process');
(async () => {
  const user = JSON.parse(fs.readFileSync('/checks/credentials.json', 'utf8'));
  const inventory = JSON.parse(fs.readFileSync('/checks/inventory-before.json', 'utf8'));
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, baseURL: 'http://frontend', acceptDownloads: true });
  const page = await context.newPage();
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  const started = Date.now();
  try {
    await page.goto('/');
    await page.getByLabel('Email address', { exact: true }).fill(user.email);
    await page.getByLabel('Password', { exact: true }).fill(user.password);
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(page.getByRole('button', { name: 'New matter', exact: true })).toBeVisible({ timeout: 30000 });
    const module = await context.request.get('/api/commercial-modules/active');
    expect(module.ok()).toBe(true); expect((await module.json()).enabled).toBe(true);
    let checked = 0;
    const cases = [...new Set(inventory.balances.map(row => row.case_id))];
    for (const id of cases) {
      const response = await context.request.get(`/api/cases/${id}/ledger`);
      expect(response.ok()).toBe(true);
      const ledger = await response.json();
      for (const row of inventory.balances.filter(row => row.case_id === id)) {
        expect(ledger[row.account_type].balance_pence).toBe(Number(row.balance_pence)); checked++;
      }
    }
    const original = await context.request.get(`/api/cases/${user.case_id}/files/${user.file_id}`);
    expect(original.ok()).toBe(true);
    expect(crypto.createHash('sha256').update(await original.body()).digest('hex')).toBe(user.original_hash);
    await page.getByRole('textbox', { name: 'Search cases', exact: true }).fill(user.case_number);
    const row = page.getByRole('row').filter({ hasText: user.case_number });
    await expect(row).toBeVisible(); await row.dblclick();
    await expect(page.getByRole('heading', { name: user.title, exact: true })).toBeVisible();
    const file = page.getByText(user.filename, { exact: true }); await expect(file).toBeVisible();
    await page.screenshot({ path: '/checks/restored-documents.png' });
    const popup = page.waitForEvent('popup'); await file.dblclick(); const editor = await popup;
    const office = editor.frameLocator('iframe[name="frameEditor"]');
    await expect(office.getByText('Page 1 of 1', { exact: true })).toBeVisible({ timeout: 90000 });
    const input = office.locator('#area_id'); await input.focus(); await input.press('Control+End'); await input.press('Enter');
    const marker = 'RESTORE-DRILL-VERIFIED-' + Date.now(); await input.pressSequentially(marker);
    await editor.getByRole('button', { name: 'Save Changes', exact: true }).click();
    await expect(editor.getByRole('button', { name: 'Save Changes', exact: true })).toBeEnabled({ timeout: 90000 });
    await editor.getByRole('button', { name: 'Close', exact: true }).click();
    await file.click({ button: 'right' }); const download = page.waitForEvent('download');
    await page.getByRole('menuitem', { name: 'Download', exact: true }).click();
    const destination = '/checks/restored-edited.docx'; await (await download).saveAs(destination);
    const xml = execFileSync('python3', ['-c', 'import sys,zipfile; print(zipfile.ZipFile(sys.argv[1]).read("word/document.xml").decode())', destination], { encoding: 'utf8' });
    expect(xml).toContain(marker);
    await page.getByRole('button', { name: 'Sign out', exact: true }).click();
    const logout = page.waitForResponse(r => r.url().endsWith('/api/auth/logout') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Sign out', exact: true }).last().click();
    expect((await logout).ok()).toBe(true); expect((await context.request.get('/api/auth/me')).status()).toBe(401);
    expect(errors).toEqual([]);
    const result = { login: true, commercial_module: true, ledger_accounts_checked: checked, ledger_cases_checked: cases.length, original_document_hash_matches: true, edit_save_download: true, logout: true, browser_errors: 0, verification_seconds: (Date.now() - started) / 1000 };
    fs.writeFileSync('/checks/browser-results.json', JSON.stringify(result, null, 2)); console.log(JSON.stringify(result));
  } catch (error) { await page.screenshot({ path: '/checks/verification-failure.png' }); throw error; }
  finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
