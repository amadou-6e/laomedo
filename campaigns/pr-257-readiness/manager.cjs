// Native private runtime, synthetic profile only. No GitHub credential or exchange.
const path = require('path');
const crypto = require('crypto');
const runtime = path.join(process.env.TEMP, 'laomedo-graph-20261107');
const { chromium } = require(path.join(runtime, 'upstream-langflow/src/frontend/node_modules/@playwright/test'));
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  try {
    const page = await context.newPage();
    await page.goto('http://127.0.0.1:17867/login');
    const pin = '0' + String(crypto.randomInt(10000, 100000));
    await page.getByRole('button', { name: /^create another profile$/i }).click();
    await page.getByLabel('Profile name', { exact: true }).fill('Manager QA ' + Date.now().toString().slice(-6));
    await page.getByLabel('PIN (6 digits)', { exact: true }).fill(pin);
    await page.getByLabel('Confirm PIN', { exact: true }).fill(pin);
    await page.getByRole('button', { name: /^create profile$/i }).click();
    await page.waitForURL('http://127.0.0.1:17867/', { timeout: 60000 });
    await page.goto('http://127.0.0.1:17867/settings/github');
    await page.getByRole('button', { name: 'View App Setup', exact: true }).waitFor({ timeout: 60000 });
    const response = await page.evaluate(async () => {
      const index = await fetch('/api/v1/laomedo/github-connections', { headers: {} });
      const body = await index.json();
      const refused = await fetch('/api/v1/laomedo/github-connections/token', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: 'synthetic-never-forwarded' }),
      });
      return { indexStatus: index.status, readyConnections: body.index?.connections.length, pending: body.index?.pending.length, csrfRefusal: refused.status, code: (await refused.json()).code };
    });
    if (response.indexStatus !== 200 || response.csrfRefusal !== 409 || response.code !== 'private_request_refused') throw new Error('Native manager admission mismatch');
    await page.screenshot({ path: path.join(process.cwd(), '.tools/pr-readiness/257-manager-empty.png'), fullPage: true });
    await page.getByRole('button', { name: 'View App Setup', exact: true }).click();
    await page.getByLabel('App client secret').waitFor();
    await page.screenshot({ path: path.join(process.cwd(), '.tools/pr-readiness/257-manager-setup.png'), fullPage: true });
    console.log(JSON.stringify({ ...response, nativeManager: true, githubRequests: 0 }));
  } finally { await context.close(); await browser.close(); }
})().catch(error => { console.error(error.message); process.exit(1); });
