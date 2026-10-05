// Disposable setup inspection only: create a saved flow, do not run a case.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright-core');

const base = 'http://127.0.0.1:7864';
const root = path.resolve(__dirname, '..', '..');
const privateRoot = path.join(__dirname, 'private-state');
fs.mkdirSync(privateRoot, { recursive: true });

async function main() {
  const auth = await (await fetch(`${base}/api/v1/auto_login`)).json();
  if (!auth.access_token) throw new Error('disposable_auto_login_unavailable');
  const flow = JSON.parse(fs.readFileSync(path.join(root, 'examples/native-codex-node/flow.json')));
  flow.id = crypto.randomUUID();
  flow.name = 'EXP-89 UI Stop inspection';
  const agent = flow.data.nodes.find(node => node.data.type === 'LaomedoCodexAgent');
  agent.data.node.template.runner_url.value = 'http://host.docker.internal:8768';
  agent.data.node.template.timeout_seconds.value = 15;
  agent.data.node.template.operation.value = 'fresh';
  const response = await fetch(`${base}/api/v1/flows/`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${auth.access_token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(flow),
  });
  if (!response.ok) throw new Error(`flow_create_${response.status}`);
  const created = await response.json();
  fs.writeFileSync(path.join(privateRoot, 'flow-id.txt'), created.id, 'utf8');
  const context = await chromium.launchPersistentContext(path.join(__dirname, 'browser-profile'), {
    headless: true,
    executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    args: ['--no-sandbox'],
    viewport: { width: 1440, height: 900 },
  });
  try {
    const page = await context.newPage();
    await page.goto(`${base}/flow/${created.id}`, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: path.join(privateRoot, 'inspection.png') });
    const buttons = await page.locator('button').evaluateAll(nodes => nodes.map(node => ({
      text: node.textContent?.trim().slice(0, 80),
      title: node.getAttribute('title'),
      aria: node.getAttribute('aria-label'),
      testId: node.getAttribute('data-testid'),
    })).filter(item => item.text || item.title || item.aria || item.testId));
    const inputs = await page.locator('textarea, input, [contenteditable="true"]').evaluateAll(nodes => nodes.map(node => ({
      tag: node.tagName,
      placeholder: node.getAttribute('placeholder'),
      aria: node.getAttribute('aria-label'),
      testId: node.getAttribute('data-testid'),
    })));
    console.log(JSON.stringify({ flow_id: created.id, url: page.url(), buttons, inputs }, null, 2));
  } finally {
    await context.close();
  }
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
