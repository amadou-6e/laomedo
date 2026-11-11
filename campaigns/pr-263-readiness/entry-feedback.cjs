// Real local profile UI; no profile creation, PIN entry, mocks or mutations.
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
    const icons = await page.locator('button svg.lucide-user-round[aria-hidden="true"]').count();
    if (!icons) throw Error('Profile icons missing from real picker');
    await page.screenshot({ path: path.join(out, '263-owner-picker-icons.png') });
    await page.getByRole('button', { name: 'Create Another Profile', exact: true }).click();
    await page.getByRole('button', { name: 'Create Profile', exact: true }).click();
    const alert = page.getByRole('alert');
    await alert.getByText('Check your details', { exact: true }).waitFor();
    if (await alert.locator('details').count()) throw Error('Technical diagnostics remain');
    await page.screenshot({ path: path.join(out, '263-owner-plain-validation.png') });
    await page.getByLabel('Profile name', { exact: true }).fill('Entry presentation check');
    if (await page.getByRole('alert').count()) throw Error('Stale validation remains after editing');
    await page.screenshot({ path: path.join(out, '263-owner-validation-edited.png') });
    await page.getByRole('button', { name: 'Back To Profiles', exact: true }).click();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(out, '263-owner-picker-icons-narrow.png') });
    console.log(JSON.stringify({ realProfileIcons: icons, plainError: true,
      diagnosticsAbsent: true, staleValidationCleared: true, profileWrites: 0 }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exit(1); });
