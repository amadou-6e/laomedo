import test from 'node:test';
import assert from 'node:assert/strict';
import {projectDevice, projectIdentity} from './native-login.mjs';

const device = {type: 'chatgptDeviceCode', loginId: '12345678-1234-1234-1234-123456789abc',
  verificationUrl: 'https://auth.openai.com/codex/device', userCode: 'ABCD-1234'};
test('device handoff admits only the exact official endpoint and bounded code', () => {
  assert.deepEqual(projectDevice(device), {type: 'device', authorization_url: device.verificationUrl, user_code: device.userCode});
  for (const update of [{verificationUrl: device.verificationUrl + '?code=ABCD'},
    {verificationUrl: 'https://auth.openai.com.evil.test/codex/device'},
    {verificationUrl: 'https://auth.openai.com@evil.test/codex/device'},
    {userCode: 'x'.repeat(65536)}, {userCode: '---'}, {userCode: 'AB'}, {userCode: 'ABC'}, {loginId: 'unknown'}]) {
    assert.throws(() => projectDevice({...device, ...update}), /^Error: provider_sign_in_failed$/);
  }
});
test('identity uses only native public observations and fails closed on ambiguity', () => {
  const response = {requiresOpenaiAuth: true, account: {type: 'chatgpt', email: 'test@example.invalid', planType: 'plus'},
    workspaceRouting: {chatgptAccountId: 'account_123', accountRoutingOverride: 'NO_CONSTRAINT'}};
  const identity = projectIdentity(response, {accountId: 'account_123', ignoredSecret: 'private-fixture'});
  assert.deepEqual(identity, {type: 'identity', email: 'test@example.invalid', account_id: 'account_123', plan_type: 'plus'});
  assert.equal(JSON.stringify(identity).includes('private-fixture'), false);
  assert.deepEqual(projectIdentity(response), identity);
  assert.deepEqual(projectIdentity({...response, workspaceRouting: null}, {accountId: 'account_123'}), identity);
  for (const invalid of [{}, {...response, requiresOpenaiAuth: false},
    {...response, account: {...response.account, type: 'apiKey'}},
    {...response, workspaceRouting: {...response.workspaceRouting, accountRoutingOverride: 'US_CR'}}]) {
    assert.throws(() => projectIdentity(invalid), /^Error: provider_sign_in_failed$/);
  }
  assert.throws(() => projectIdentity(response, {accountId: 'different-account'}), /^Error: provider_sign_in_failed$/);
  assert.throws(() => projectIdentity({...response, workspaceRouting: null}), /^Error: provider_sign_in_failed$/);
});
