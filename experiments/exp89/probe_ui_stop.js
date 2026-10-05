// EXP-89: browser-driven UI Stop probe against disposable Langflow and fake runner.
// Commit this script before any case. No real model, GitHub write, or external agent.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright-core');

const base = 'http://127.0.0.1:7864';
const root = path.resolve(__dirname, '..', '..');
const privateRoot = path.join(__dirname, 'private-state');
const cases = {
  A: { operation: 'start', task: 'CASE_A synthetic stop probe', event: 'post_received' },
  B: { operation: 'fresh', task: 'CASE_B synthetic stop probe', event: 'synthetic_wait_started' },
  CONTROL: { operation: 'fresh', task: 'CONTROL synthetic stop probe', event: 'response_sent' },
};

function journal() {
  const file = path.join(privateRoot, 'journal.jsonl');
  if (!fs.existsSync(file)) return [];
  return fs.readFileSync(file, 'utf8').trim().split('\n').filter(Boolean).map(line => JSON.parse(line));
}

function at() { return new Date().toISOString(); }

async function waitForEvent(kind, baseline, timeoutMs) {
  const until = Date.now() + timeoutMs;
  while (Date.now() < until) {
    const event = journal().slice(baseline).find(item => item.kind === kind);
    if (event) return event;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  return null;
}

async function buttons(page) {
  return page.locator('button').evaluateAll(nodes => nodes.map(node => ({
    text: node.textContent?.trim().slice(0, 80) || '',
    title: node.getAttribute('title') || '',
    aria: node.getAttribute('aria-label') || '',
    testId: node.getAttribute('data-testid') || '',
    disabled: node.disabled,
    visible: !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length),
  })).filter(item => item.visible && /stop|cancel|abort/i.test([item.text, item.title, item.aria, item.testId].join(' '))));
}

async function main() {
  const name = process.argv[2];
  if (!Object.hasOwn(cases, name)) throw new Error('expected_A_B_or_CONTROL');
  fs.mkdirSync(privateRoot, { recursive: true });
  const output = path.join(privateRoot, `case-${name.toLowerCase()}.json`);
  if (fs.existsSync(output)) throw new Error('case_already_recorded_no_retry');
  const chosen = cases[name];
  const observation = { case: name, probe_started_utc: at(), browser_requests: [], runner_baseline: journal().length };
  const auth = await (await fetch(`${base}/api/v1/auto_login`)).json();
  if (!auth.access_token) throw new Error('disposable_auto_login_unavailable');
  const flow = JSON.parse(fs.readFileSync(path.join(root, 'examples/native-codex-node/flow.json'), 'utf8'));
  flow.id = crypto.randomUUID();
  flow.name = `EXP-89 Case ${name}`;
  const agent = flow.data.nodes.find(node => node.data.type === 'LaomedoCodexAgent');
  agent.data.node.template.runner_url.value = 'http://host.docker.internal:8768';
  agent.data.node.template.timeout_seconds.value = 15;
  agent.data.node.template.operation.value = chosen.operation;
  const response = await fetch(`${base}/api/v1/flows/`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${auth.access_token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(flow),
  });
  if (!response.ok) throw new Error(`flow_create_${response.status}`);
  const created = await response.json();
  observation.flow_id = created.id;
  const context = await chromium.launchPersistentContext(path.join(__dirname, `browser-profile-${name.toLowerCase()}`), {
    headless: true,
    executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    args: ['--no-sandbox'],
    viewport: { width: 1440, height: 900 },
  });
  try {
    const page = await context.newPage();
    page.on('request', request => {
      const url = new URL(request.url());
      if (url.hostname === '127.0.0.1' && url.port === '7864' &&
          /run|stop|cancel|job/.test(url.pathname)) {
        observation.browser_requests.push({ at_utc: at(), method: request.method(), path: url.pathname });
      }
    });
    await page.goto(`${base}/flow/${created.id}`, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.getByTestId('playground-btn-flow-io').click({ timeout: 30000 });
    await page.getByTestId('input-chat-playground').waitFor({ timeout: 30000 });
    await page.getByTestId('input-chat-playground').fill(chosen.task);
    observation.send_clicked_utc = at();
    await page.getByTestId('button-send').click();
    const event = await waitForEvent(chosen.event, observation.runner_baseline, 20000);
    observation.target_event = event ? { kind: event.kind, run_id: event.run_id, at_utc: event.at_utc } : null;
    observation.buttons_at_target = await buttons(page);
    await page.screenshot({ path: path.join(privateRoot, `case-${name.toLowerCase()}-before.png`) });
    const stop = observation.buttons_at_target.find(item => !item.disabled);
    if (stop) {
      let locator = stop.testId ? page.getByTestId(stop.testId) :
        stop.aria ? page.getByRole('button', { name: stop.aria, exact: true }) :
        stop.title ? page.locator(`button[title=${JSON.stringify(stop.title)}]`) :
        page.getByRole('button', { name: stop.text, exact: true });
      observation.stop_clicked_utc = at();
      observation.stop_control = stop;
      await locator.first().click({ timeout: 3000 });
    } else {
      observation.stop_control = null;
    }
    await page.waitForTimeout(8000);
    observation.buttons_after_wait = await buttons(page);
    await page.screenshot({ path: path.join(privateRoot, `case-${name.toLowerCase()}-after.png`) });
  } catch (error) {
    observation.probe_error = String(error.message).slice(0, 250);
  } finally {
    await context.close();
    observation.probe_finished_utc = at();
    observation.runner_events = journal().slice(observation.runner_baseline).map(({ kind, run_id, at_utc, case: runner_case, operation, status, known }) =>
      ({ kind, run_id, at_utc, case: runner_case, operation, status, known }));
    fs.writeFileSync(output, JSON.stringify(observation, null, 2) + '\n', { encoding: 'utf8', flag: 'wx' });
    console.log(JSON.stringify(observation, null, 2));
  }
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
