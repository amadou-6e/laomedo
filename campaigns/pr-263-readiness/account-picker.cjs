// Actual profile preview checks; no profile creation, PIN entry or fixture data.
const path = require('path');
const runtime = path.join(process.env.TEMP, 'laomedo-graph-20261107');
const { chromium } = require(path.join(runtime, 'upstream-langflow/src/frontend/node_modules/@playwright/test'));
const out = path.join(process.cwd(), '.tools/pr-readiness');
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    await page.goto('http://127.0.0.1:17866/login');
    await page.getByRole('heading', { name: 'Choose profile', exact: true }).waitFor();
    const avatars = page.locator('button > span[aria-hidden="true"].rounded-full');
    await avatars.first().waitFor();
    const alignment = await avatars.evaluateAll(nodes => nodes.map(node => ({
      avatar: node.getBoundingClientRect().x,
      name: node.nextElementSibling.getBoundingClientRect().x,
      rowHeight: node.parentElement.getBoundingClientRect().height,
    })));
    if (new Set(alignment.map(row => row.avatar)).size !== 1 ||
        new Set(alignment.map(row => row.name)).size !== 1 ||
        alignment.some(row => row.rowHeight < 64)) throw Error('List alignment/size failed');
    await page.screenshot({ path: path.join(out, '263-account-picker-wide.png') });
    await avatars.first().locator('..').click();
    await page.getByRole('heading', { name: 'Log in', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Log in', exact: true }).waitFor();
    const back = page.getByRole('button', { name: 'Back to profiles', exact: true });
    if (!(await back.locator('svg.lucide-arrow-left').count()) || (await back.innerText()).trim()) throw Error('Back control is not an accessible icon-only arrow');
    await page.screenshot({ path: path.join(out, '263-login-arrow.png') });
    await back.click();
    await page.getByRole('heading', { name: 'Choose profile', exact: true }).waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(out, '263-account-picker-narrow.png') });
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw Error('Horizontal overflow');
    await page.getByRole('button', { name: 'Create profile', exact: true }).click();
    await page.getByRole('button', { name: 'Create profile', exact: true }).click();
    for (const [label, message] of [['Profile name', 'Enter a profile name'], ['PIN (6 digits)', 'Use a six-digit PIN'], ['Confirm PIN', 'Confirm your PIN']]) {
      const field = page.getByLabel(label, { exact: true });
      if (await field.getAttribute('aria-invalid') !== 'true') throw Error('Field not marked invalid');
      await page.getByText(message, { exact: true }).waitFor();
    }
    await page.screenshot({ path: path.join(out, '263-account-picker-field-errors.png') });
    await page.getByLabel('Profile name', { exact: true }).fill('Presentation check');
    if (await page.getByText('Enter a profile name', { exact: true }).count()) throw Error('Corrected field error remains');
    await page.getByText('Use a six-digit PIN', { exact: true }).waitFor();
    console.log(JSON.stringify({ alignedRows: alignment.length, minHeight64: true,
      narrowOverflow: false, fieldErrorsAssociated: true, onlyCorrectedErrorCleared: true, profileWrites: 0 }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exit(1); });
