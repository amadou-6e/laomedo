const fs = require('fs'); const path = require('path');
const { chromium, expect } = require('@playwright/test');
let browser;
(async () => {
  browser = await chromium.launch({channel: 'msedge'});
  const context = await browser.newContext({viewport: {width: 1400, height: 1000}});
  const page = await context.newPage(); let reads = 0;
  await page.route('**/api/v1/laomedo/github-issues/inspect', route => {
    const selected = route.request().postDataJSON(); reads++;
    return route.fulfill({json: {
      schema_version: 'laomedo.issue-inspection.v1',
      issue: {repository: 'fixture/repo', number: selected.issue_number,
        url: selected.repository_url.replace(/\/$/, '') + '/issues/' + selected.issue_number,
        title: 'Readable issue fixture', state: 'open', labels: ['bug', 'enhancement'],
        updated_at: '2026-10-13T11:50:44Z',
        body: '**Rendered markdown**\n\n' + Array(40).fill('A readable paragraph with enough text to exercise scrolling.').join('\n\n') + '\n\n<img src="https://external.invalid/a" onerror="window.issueInjected=1" />'},
      fetched_at: new Date(Date.UTC(2026, 9, 13, 12, 0, reads)).toISOString(),
    }});
  });
  if (process.argv[3]) {
    const build = path.resolve(process.argv[3]);
    await page.route('**/*', route => {
      const request = route.request(); const url = new URL(request.url());
      if (url.origin !== new URL(process.argv[2]).origin) return route.continue();
      const relative = request.isNavigationRequest() ? 'index.html' : decodeURIComponent(url.pathname).replace(/^\//, '');
      const file = path.resolve(build, relative);
      if (!file.startsWith(build + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return route.fallback();
      const extension = path.extname(file);
      const mime = {'.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.json': 'application/json'};
      return route.fulfill({path: file, contentType: mime[extension] || 'application/octet-stream'});
    });
  }
  await page.goto(process.argv[2]);
  const node = page.locator('.react-flow__node[data-id="issue"]');
  await node.waitFor({timeout: 60000}); await node.click();
  await page.getByTestId('issue-viewer-button').click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByTestId('issue-viewer-content')).toContainText('Readable issue fixture');
  await expect(dialog.getByRole('button', {name: 'Issue viewer', exact: true})).toHaveCount(0);
  await expect(dialog.getByRole('heading', {name: /Readable issue fixture/})).toBeVisible();
  await expect(dialog.locator('strong')).toHaveText('Rendered markdown');
  await expect(dialog.locator('img')).toHaveCount(0);
  expect(await page.evaluate(() => window.issueInjected)).toBeUndefined();
  const actions = dialog.getByTestId('issue-viewer-actions');
  const refresh = actions.getByRole('button', {name: 'Refresh issue'});
  await expect(refresh).toBeVisible(); await refresh.click();
  await expect.poll(() => reads).toBe(2);
  await expect(dialog.locator('time').last()).toHaveAttribute('datetime', '2026-10-13T12:00:02.000Z');
  for (const width of [1400, 700]) {
    await page.setViewportSize({width, height: 860});
    await expect(refresh).toBeVisible();
    await expect(actions.getByTestId('issue-open-browser')).toHaveAttribute('rel', 'noopener noreferrer');
    await expect.poll(async () => {
      const box = await actions.boundingBox(); const panel = await dialog.boundingBox();
      return box.y > panel.y + panel.height / 2 &&
        box.x + box.width <= panel.x + panel.width &&
        panel.x + panel.width - box.x - box.width < 35 &&
        box.y + box.height <= 860;
    }).toBe(true);
  }
  await page.keyboard.press('Escape'); await expect(dialog).toHaveCount(0);
  console.log('PASS: readable issue layout, no redundant button, fixed footer at desktop/compact widths, mocked read-only refresh and safe Markdown. No model or GitHub write.');
})().catch(e => {console.error(e); process.exitCode = 1}).finally(async () => {if (browser) await browser.close()});

