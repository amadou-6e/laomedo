/** Fixed native ChatGPT sign-in boundary. Never a browser-to-native RPC tunnel. */
import { spawn } from 'node:child_process';
import { access } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

const failure = () => new Error('provider_sign_in_failed');

export function projectDevice(value) {
  if (value?.type !== 'chatgptDeviceCode'
      || value.verificationUrl !== 'https://auth.openai.com/codex/device'
      || typeof value.userCode !== 'string' || (value.userCode.length < 4 || value.userCode.length > 32)
      || !/^[A-Z0-9]{2,16}(?:-[A-Z0-9]{2,16})?$/.test(value.userCode)
      || typeof value.loginId !== 'string'
      || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(value.loginId)) throw failure();
  return {type: 'device', authorization_url: value.verificationUrl, user_code: value.userCode};
}

export function projectIdentity(response, quota) {
  const account = response?.account;
  const routing = response?.workspaceRouting;
  const routedId = routing?.chatgptAccountId;
  const meteredId = quota?.accountId;
  const accountId = routedId ?? meteredId;
  if (response?.requiresOpenaiAuth !== true || account?.type !== 'chatgpt'
      || typeof account.email !== 'string' || !account.email.trim() || account.email.length > 100
      || typeof accountId !== 'string' || !/^[A-Za-z0-9_-]{1,200}$/.test(accountId)
      || typeof account.planType !== 'string' || !account.planType || account.planType.length > 64
      || (routedId != null && meteredId != null && routedId !== meteredId)
      || (routing != null && routing.accountRoutingOverride !== 'NO_CONSTRAINT')) throw failure();
  return {type: 'identity', email: account.email, account_id: accountId, plan_type: account.planType};
}

class NativeAccountClient {
  constructor() {
    this.child = spawn('/usr/local/bin/codex', ['app-server', '--listen', 'stdio://',
      '-c', 'cli_auth_credentials_store="file"', '-c', 'forced_login_method="chatgpt"', '-c', 'model_provider="openai"'],
      {stdio: ['pipe', 'pipe', 'ignore'], env: {PATH: process.env.PATH, HOME: '/home/runner',
        CODEX_HOME: '/home/runner/.codex', CODEX_APP_SERVER_LOGIN_ISSUER: 'https://auth.openai.com', LANG: 'C.UTF-8'}});
    this.pending = new Map();
    this.sequence = 0;
    this.buffer = '';
    this.notifications = [];
    this.closed = new Promise(resolve => this.child.once('close', resolve));
    this.child.once('error', () => this.fail());
    this.child.stdin.on('error', () => this.fail());
    this.child.once('exit', () => this.fail());
    this.child.stdout.setEncoding('utf8');
    this.child.stdout.on('data', chunk => {
      this.buffer += chunk;
      if (this.buffer.length > 131072) { this.fail(); this.child.kill(); return; }
      let end;
      while ((end = this.buffer.indexOf('\n')) >= 0) {
        const line = this.buffer.slice(0, end); this.buffer = this.buffer.slice(end + 1);
        if (!line.trim()) continue;
        try { this.receive(JSON.parse(line)); } catch { this.fail(); this.child.kill(); }
      }
    });
  }
  fail() {
    for (const item of this.pending.values()) item.reject(failure());
    this.pending.clear();
    if (this.completionReject) this.completionReject(failure());
  }
  receive(value) {
    if (value.id !== undefined && (value.result !== undefined || value.error !== undefined)) {
      const item = this.pending.get(value.id);
      if (!item) return;
      this.pending.delete(value.id);
      if (value.error !== undefined) item.reject(failure()); else item.resolve(value.result);
    } else if (value.id !== undefined) {
      this.child.stdin.write(JSON.stringify({id: value.id, error: {code: -32601, message: 'Unsupported request'}}) + '\n');
    } else if (value.method === 'account/login/completed') {
      if (this.completionResolve) this.completionResolve(value.params);
      else if (this.notifications.length < 4) this.notifications.push(value.params);
      else throw failure();
    }
  }
  request(method, params) {
    const id = ++this.sequence;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(failure()); }, 30000);
      this.pending.set(id, {resolve: value => { clearTimeout(timer); resolve(value); },
        reject: error => { clearTimeout(timer); reject(error); }});
      this.child.stdin.write(JSON.stringify({id, method, params}) + '\n');
    });
  }
  async initialize() {
    await this.request('initialize', {clientInfo: {name: 'laomedo', title: 'Laomedo', version: '0.1.0'}, capabilities: {experimentalApi: true}});
    this.child.stdin.write(JSON.stringify({method: 'initialized', params: {}}) + '\n');
  }
  async login() {
    const value = await this.request('account/login/start', {type: 'chatgptDeviceCode'});
    const publicCode = projectDevice(value);
    process.stdout.write(JSON.stringify(publicCode) + '\n');
    const completion = await new Promise((resolve, reject) => {
      this.completionResolve = resolve; this.completionReject = reject;
      const queued = this.notifications.shift(); if (queued) resolve(queued);
    });
    if (completion?.loginId !== value.loginId || completion.success !== true) throw failure();
  }
  async identity() {
    const response = await this.request('account/read', {refreshToken: false});
    let quota;
    try { quota = await this.request('account/rateLimits/read', {}); } catch { /* No inferred zero allowance. */ }
    return projectIdentity(response, quota);
  }
  async stop() {
    this.child.stdin.end();
    let timer;
    timer = setTimeout(() => this.child.kill('SIGKILL'), 3000);
    await this.closed;
    clearTimeout(timer);
    this.fail();
  }
}

async function main() {
  if (!['login', 'identity'].includes(process.argv[2]) || process.argv.length !== 3) throw failure();
  const client = new NativeAccountClient();
  const lifetime = setTimeout(() => { client.fail(); client.child.kill('SIGKILL'); }, 900000);
  let identity;
  try {
    await client.initialize();
    if (process.argv[2] === 'login') await client.login();
    identity = await client.identity();
  } finally { clearTimeout(lifetime); await client.stop(); }
  await access('/home/runner/.codex/auth.json');
  process.stdout.write(JSON.stringify(identity) + '\n');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(() => { process.stdout.write('{"type":"failed","code":"provider_sign_in_failed"}\n'); process.exitCode = 1; });
}
