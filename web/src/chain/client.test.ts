import { describe, it, expect } from 'vitest';
import { canUseLocalDemo, parseDeployment } from './client';
const valid = { chainId: 31337, name: 'Local', rpcUrl: 'http://127.0.0.1:18547', address: '0x1111111111111111111111111111111111111111',
  token: '0x2222222222222222222222222222222222222222', runtimeCodeHash: '0x' + 'aa'.repeat(32), tokenDecimals: 18, tokenSymbol: 'DEMO',
  feeBps: 250, feeRecipient: '0x3333333333333333333333333333333333333333', confirmations: 1, testOnly: true };
describe('settlement deployment boundary', () => {
  it('accepts local test and secure public RPC', () => {
    expect(parseDeployment(valid).chainId).toBe(31337);
    expect(parseDeployment({ ...valid, rpcUrl: 'https://rpc.example.com' }).rpcUrl).toBe('https://rpc.example.com/');
  });
  it.each(['http://rpc.example.com', 'javascript:alert(1)', 'https://user:password@example.com'])('rejects unsafe RPC %s', rpcUrl => {
    expect(() => parseDeployment({ ...valid, rpcUrl })).toThrow();
  });
  it.each([{ confirmations: 0 }, { confirmations: 1.5 }, { chainId: -1 }, { chainId: Number.MAX_SAFE_INTEGER + 1 },
    { feeBps: 1001 }, { tokenDecimals: 37 }, { token: 'not-an-address' }, { runtimeCodeHash: '0x12' }, { testOnly: undefined }])('rejects malformed settlement parameters %j', change => {
    expect(() => parseDeployment({ ...valid, ...change })).toThrow();
  });
});

it('never enables unlocked demo accounts on live networks or remote RPCs', () => {
  expect(canUseLocalDemo({ ...valid, chainId: 1 })).toBe(false);
  expect(canUseLocalDemo({ ...valid, testOnly: false })).toBe(false);
  expect(canUseLocalDemo({ ...valid, rpcUrl: 'https://rpc.example.com' })).toBe(false);
  expect(canUseLocalDemo({ ...valid, rpcUrl: 'http://127.0.0.1:8545' })).toBe(false);
});
