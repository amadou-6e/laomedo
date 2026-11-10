// Real task-owned browser, synthetic QA only. PIN stays in process memory.
const path = require('path');
const crypto = require('crypto');
const runtime = path.join(process.env.TEMP, 'laomedo-graph-20261107');
const { chromium } = require(path.join(runtime, 'upstream-langflow/src/frontend/node_modules/@playwright/test'));
const out = path.join(process.cwd(), '.tools/pr-readiness');
(async () => {
  const context = await chromium.launchPersistentContext(path.join(runtime, 'readiness/profile-browser'), {
    channel: 'msedge', headless: true, viewport: { width: 1280, height: 900 },
  });
  try {
    const page = context.pages()[0] || await context.newPage();
    await page.goto('http://127.0.0.1:17866/login');
    await page.getByRole('heading', { name: 'Choose profile' }).waitFor({ timeout: 60000 });
    await page.getByRole('button', { name: 'Readiness QA', exact: true }).waitFor();
    await page.screenshot({ path: path.join(out, '263-picker-case-fixed.png'), fullPage: true });
    const pin = '0' + String(crypto.randomInt(10000, 100000));
    for (const name of ['Readiness QA', '__laomedo_system__']) {
      await page.getByRole('button', { name: /^create another profile$/i }).click();
      await page.getByLabel('Profile name', { exact: true }).fill(name);
      await page.getByLabel('PIN (6 digits)', { exact: true }).fill(pin);
      await page.getByLabel('Confirm PIN', { exact: true }).fill(pin);
      const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/laomedo/profiles' && r.request().method() === 'POST');
      await page.getByRole('button', { name: /^create profile$/i }).click();
      const status = (await response).status();
      await page.getByText('This name is unavailable. Your profile has not been created.').waitFor();
      await page.screenshot({ path: path.join(out, name.startsWith('__') ? '263-reserved-name.png' : '263-duplicate-name.png'), fullPage: true });
      console.log(JSON.stringify({ phase: name.startsWith('__') ? 'reserved' : 'duplicate', status }));
      await page.getByRole('button', { name: /^back to profiles$/i }).click();
    }
    const name = 'Visual QA ' + Date.now().toString().slice(-6);
    await page.getByRole('button', { name: /^create another profile$/i }).click();
    await page.getByLabel('Profile name', { exact: true }).fill(name);
    await page.getByLabel('PIN (6 digits)', { exact: true }).fill(pin);
    await page.getByLabel('Confirm PIN', { exact: true }).fill(pin);
    let committedStatus;
    await page.route('**/api/v1/laomedo/profiles', async route => {
      if (route.request().method() !== 'POST') return route.continue();
      const response = await route.fetch();
      committedStatus = response.status();
      await route.abort();
    });
    await page.getByRole('button', { name: /^create profile$/i }).click();
    await page.getByRole('button', { name: /^check profile list$/i }).waitFor();
    await page.screenshot({ path: path.join(out, '263-creation-unconfirmed.png'), fullPage: true });
    await page.unroute('**/api/v1/laomedo/profiles');
    await page.getByRole('button', { name: /^check profile list$/i }).click();
    await page.getByRole('button', { name: /^open existing profile$/i }).waitFor();
    await page.getByRole('button', { name: /^open existing profile$/i }).click();
    const pinCleared = await page.getByLabel('PIN (6 digits)', { exact: true }).inputValue() === '';
    await page.getByLabel('PIN (6 digits)', { exact: true }).fill(pin);
    await page.getByRole('button', { name: /^open profile$/i }).click();
    await page.waitForURL('http://127.0.0.1:17866/', { timeout: 45000 });
    await page.getByTestId('user-profile-settings').waitFor();
    console.log(JSON.stringify({ phase: 'lost-creation-response', committedStatus, reconciled: true, pinCleared }));
    await page.route('**/api/v1/logout', route => route.abort());
    await page.getByTestId('user-profile-settings').click();
    await page.getByRole('menuitem', { name: /^log\s*out$/i }).click();
    await page.getByRole('button', { name: /check current profile/i }).waitFor();
    const close = page.getByRole('button', { name: 'Close sign-out notice', exact: true });
    await close.waitFor();
    await page.screenshot({ path: path.join(out, '263-signout-close-fixed.png'), fullPage: true });
    await close.click();
    await page.getByRole('button', { name: /check current profile/i }).waitFor({ state: 'hidden' });
    if (new URL(page.url()).pathname !== '/') throw new Error('Dismissal claimed sign-out');
    console.log(JSON.stringify({ phase: 'close-notice', visibleControl: true, dismissedWithoutSignout: true }));
    await page.unroute('**/api/v1/logout');
    await page.getByTestId('user-profile-settings').click();
    await page.getByRole('menuitem', { name: /^switch profile$/i }).click();
    await page.waitForURL('**/login');
    await page.getByRole('button', { name, exact: true }).waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(out, '263-picker-narrow.png'), fullPage: false });
    console.log(JSON.stringify({ phase: 'narrow-picker', exactMixedCaseName: true, width: 390 }));
    await page.getByRole('button', { name: /^create another profile$/i }).click();
    await page.screenshot({ path: path.join(out, '263-create-narrow.png'), fullPage: false });
    await page.getByRole('button', { name: /^back to profiles$/i }).click();
    await page.getByRole('button', { name, exact: true }).click();
    await page.screenshot({ path: path.join(out, '263-enter-narrow.png'), fullPage: false });
    console.log(JSON.stringify({ phase: 'narrow-forms', width: 390, pinNotCaptured: true }));
  } finally { await context.close(); }
})().catch(error => { console.error(error.message); process.exit(1); });
