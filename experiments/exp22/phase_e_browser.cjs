// Disposable visible-Playground probe. Raw browser state stays outside Git.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const ROOT = path.resolve(__dirname, '..', '..');
const { chromium } = require(require.resolve('playwright-core', {
  paths: [path.join(ROOT, 'experiments/exp94')],
}));
const [mode, stateArg, uiPortArg, runnerPortArg, revision] = process.argv.slice(2);
if (!['prepare', 'run'].includes(mode) || !stateArg || !uiPortArg || !runnerPortArg || !revision) {
  throw new Error('usage: phase_e_browser.js prepare|run STATE UI_PORT RUNNER_PORT REVISION');
}
const state = path.resolve(stateArg);
const base = `http://127.0.0.1:${Number(uiPortArg)}`;
const flowFile = path.join(state, 'flow-id.txt');
const resultFile = path.join(state, `browser-${mode}.json`);
const signalFile = path.join(state, 'stop-now.signal');
const edge = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
function pause(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
function utc() { return new Date().toISOString(); }

async function main() {
  const observation = { mode, browser_requests: [], stop_clicked: false, send_clicked: false };
  const context = await chromium.launchPersistentContext(path.join(state, `browser-profile-${mode}`), {
    headless: true, executablePath: edge, args: ['--no-sandbox'],
    viewport: { width: 1440, height: 900 },
  });
  try {
    let flowId;
    if (mode === 'prepare') {
      const login = await fetch(`${base}/api/v1/auto_login`);
      if (!login.ok) throw new Error(`auto_login_${login.status}`);
      const auth = await login.json();
      if (!auth.access_token) throw new Error('disposable_auto_login_unavailable');
      const flow = JSON.parse(fs.readFileSync(path.join(ROOT, 'examples/native-codex-node/flow.json'), 'utf8'));
      flow.id = crypto.randomUUID();
      flow.name = 'EXP-22 Phase E visible Stop';
      const skill = flow.data.nodes.find(node => node.data.type === 'LaomedoSkill');
      const agent = flow.data.nodes.find(node => node.data.type === 'LaomedoCodexAgent');
      skill.data.node.template.skill_id.value = 'laomedo-pilot';
      skill.data.node.template.revision_id.value = revision;
      agent.data.node.template.runner_url.value = `http://host.docker.internal:${Number(runnerPortArg)}`;
      agent.data.node.template.timeout_seconds.value = 120;
      agent.data.node.template.operation.value = 'fresh';
      const response = await fetch(`${base}/api/v1/flows/`, {
        method: 'POST', headers: { Authorization: `Bearer ${auth.access_token}`,
                                   'Content-Type': 'application/json' },
        body: JSON.stringify(flow),
      });
      if (!response.ok) throw new Error(`flow_create_${response.status}`);
      flowId = (await response.json()).id;
      fs.writeFileSync(flowFile, flowId, { encoding: 'ascii', flag: 'wx' });
    } else {
      flowId = fs.readFileSync(flowFile, 'ascii').trim();
    }
    observation.flow_id = flowId;
    const page = await context.newPage();
    page.on('request', request => {
      const url = new URL(request.url());
      if (url.port === uiPortArg && /run|stop|cancel|job|build/.test(url.pathname)) {
        observation.browser_requests.push({ at_utc: utc(), method: request.method(),
                                             path: url.pathname });
      }
    });
    await page.goto(`${base}/flow/${flowId}`, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.getByTestId('playground-btn-flow-io').click({ timeout: 30000 });
    await page.getByTestId('input-chat-playground').waitFor({ timeout: 30000 });
    observation.playground_available = true;
    if (mode === 'run') {
      const task = fs.readFileSync(path.join(ROOT, 'experiments/exp22/PHASE-E-TASK.txt'), 'utf8');
      await page.getByTestId('input-chat-playground').fill(task);
      observation.send_clicked_utc = utc();
      await page.getByTestId('button-send').click();
      observation.send_clicked = true;
      const deadline = Date.now() + 55000;
      while (Date.now() < deadline && !fs.existsSync(signalFile)) await pause(100);
      observation.stop_signal_seen = fs.existsSync(signalFile);
      const stop = page.getByTestId('button-stop').first();
      observation.stop_control_visible = await stop.isVisible().catch(() => false);
      observation.stop_control_enabled = observation.stop_control_visible && await stop.isEnabled();
      if (observation.stop_control_enabled) {
        await stop.click({ timeout: 3000 });
        observation.stop_clicked = true;
        observation.stop_clicked_utc = utc();
      }
      await pause(9000);
    }
  } catch (error) {
    observation.error_class = error.constructor.name;
    observation.error_message = String(error.message).slice(0, 200);
  } finally {
    await context.close();
    observation.finished_utc = utc();
    fs.writeFileSync(resultFile, JSON.stringify(observation, null, 2) + '\n',
                     { encoding: 'utf8', flag: 'wx' });
    console.log(JSON.stringify(observation));
  }
  if (observation.error_class) process.exitCode = 1;
}
main().catch(error => { console.error(error.constructor.name); process.exitCode = 1; });
