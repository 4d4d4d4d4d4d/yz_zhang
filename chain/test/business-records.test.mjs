import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { JsonRpcProvider, ContractFactory, id, ZeroAddress, Wallet, parseEther } from 'ethers';
import { compile } from '../scripts/compile.mjs';

test('organizational records: authorization, immutable versions and signer snapshots', async t => {
  const node = spawn('node_modules/node/bin/node', ['node_modules/hardhat/dist/src/cli.js', 'node', '--hostname', '127.0.0.1', '--port', '18548'], { stdio: 'ignore' });
  const rpc = new JsonRpcProvider('http://127.0.0.1:18548', 31337, { staticNetwork: true, cacheTimeout: -1 }); rpc.pollingInterval = 25;
  try {
    let ready = false;
    for (let i = 0; i < 80; i++) { try { await rpc.getBlockNumber(); ready = true; break; } catch { await delay(200); } }
    assert.ok(ready);
    const [controller, alice, bob, robot, stranger, replacement] = await Promise.all([0,1,2,3,4,5].map(i => rpc.getSigner(i)));
    const [ca, aa, ba, ra, sa, na] = await Promise.all([controller, alice, bob, robot, stranger, replacement].map(s => s.getAddress()));
    const artifact = compile('BusinessRecords');
    const registry = await new ContractFactory(artifact.abi, artifact.bytecode, controller).deploy(); await registry.waitForDeployment();
    const tx = async p => (await p).wait();
    const fail = async p => assert.rejects(async () => tx(p));
    const key = id('equity-register'), financial = id('financial-period');
    const now = async () => Number((await rpc.getBlock('latest')).timestamp);
    await t.test('namespaces and policies require nonzero distinct signers and meaningful quorum', async () => {
      await fail(registry.createOrganization(id('identity'), [aa, aa], 2));
      await fail(registry.createOrganization(id('identity'), [aa, ba], 0));
      await fail(registry.createOrganization(id('identity'), [aa, ZeroAddress], 2));
      await tx(registry.createOrganization(id('identity'), [aa, ba], 2));
      assert.equal((await registry.organizations(1)).controller, ca);
      await fail(registry.connect(stranger).setPolicy(1, [sa], 1));
      await fail(registry.connect(stranger).append(1, key, 0, 0, id('v1'), false));
      await fail(registry.append(999, key, 0, 0, id('v1'), false));
    });
    await t.test('four record categories are separated; append cannot overwrite or change category', async () => {
      for (let k = 0; k < 4; k++) await tx(registry.append(1, k === 0 ? key : k === 3 ? financial : id(`record-${k}`), 0, k, id(`v1-${k}`), false));
      const v1 = await registry.records(1, key, 1);
      await fail(registry.append(1, key, 0, 0, id('overwrite'), false));
      await fail(registry.append(1, key, 1, 3, id('category swap'), true));
      await tx(registry.append(1, key, 1, 0, id('correction-v2'), true));
      const v2 = await registry.records(1, key, 2);
      assert.equal(v2.previous, v1.recordHash); assert.equal(v2.correction, true);
      assert.equal((await registry.records(1, key, 1)).commitment, v1.commitment);
      assert.notEqual(v1.recordHash, v2.recordHash);
    });
    await t.test('only designated wallets attest, no replay and no transfer of approval to another version', async () => {
      const r = await registry.records(1, key, 1);
      await fail(registry.connect(controller).attest(1, key, 1, r.recordHash, true));
      await fail(registry.connect(alice).attest(1, key, 2, r.recordHash, true));
      await tx(registry.connect(alice).attest(1, key, 1, r.recordHash, true));
      assert.equal(await registry.isApproved(1, key, 1), false);
      await fail(registry.connect(alice).attest(1, key, 1, r.recordHash, true));
      await tx(registry.connect(bob).attest(1, key, 1, r.recordHash, true));
      assert.equal(await registry.isApproved(1, key, 1), true);
      assert.equal(await registry.isApproved(1, key, 2), false);
      await tx(registry.connect(alice).attest(1, key, 1, r.recordHash, false));
      assert.equal(await registry.isApproved(1, key, 1), false);
      const history = await registry.queryFilter(registry.filters.Attested(r.recordHash));
      assert.equal(history.length, 3, 'withdrawal retains prior attestations as immutable events');
    });
    await t.test('changing policy affects only future versions', async () => {
      await tx(registry.setPolicy(1, [na], 1));
      await tx(registry.append(1, key, 2, 0, id('v3'), false));
      const old = await registry.records(1, key, 2), fresh = await registry.records(1, key, 3);
      assert.equal(old.quorum, 2n); assert.equal(fresh.quorum, 1n);
      assert.deepEqual(Array.from(await registry.getSigners(old.recordHash)), [aa, ba]);
      await fail(registry.connect(replacement).attest(1, key, 2, old.recordHash, true));
      await tx(registry.connect(replacement).attest(1, key, 3, fresh.recordHash, true));
      assert.equal(await registry.isApproved(1, key, 3), true);
    });
    await t.test('machine publishing is category scoped, expiring and independently revocable; it never implies approval', async () => {
      await tx(registry.setGrant(1, ra, 8, await now() + 60));
      await fail(registry.connect(robot).append(1, key, 3, 0, id('unauthorized equity'), true));
      await tx(registry.connect(robot).append(1, financial, 1, 3, id('financial-v2'), false));
      const r = await registry.records(1, financial, 2);
      assert.equal(r.approvals, 0n);
      await fail(registry.connect(robot).attest(1, financial, 2, r.recordHash, true));
      await tx(registry.setGrant(1, ra, 0, 0));
      await fail(registry.connect(robot).append(1, financial, 2, 3, id('revoked'), true));
      const expires = await now() + 10; await tx(registry.setGrant(1, ra, 8, expires));
      await rpc.send('evm_setNextBlockTimestamp', [expires + 1]); await rpc.send('evm_mine', []);
      await fail(registry.connect(robot).append(1, financial, 2, 3, id('expired'), true));
    });
    await t.test('records deployment script supports dry-run and idempotent receipt recovery', async () => {
      const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'opc-records-deploy-')), run = promisify(execFile);
      const wallet = Wallet.createRandom(), keyFile = path.join(dir, 'key');
      fs.writeFileSync(keyFile, wallet.privateKey, { mode: 0o600 });
      const env = { ...process.env, CHAIN_RPC_URL: 'http://127.0.0.1:18548', CHAIN_ID: '31337', CHAIN_CONFIRMATIONS: '1', CHAIN_KEY_FILE: keyFile,
        CHAIN_RECEIPT_FILE: path.join(dir, 'receipt.json'), RECORDS_MANIFEST_FILE: path.join(dir, 'manifest.json'),
        RECORDS_PUBLIC_RPC_URL: 'http://127.0.0.1:18548', RECORDS_NETWORK_NAME: 'Integration', RECORDS_TEST_ONLY: '1', CHAIN_SEND: '0' };
      try {
        assert.equal(JSON.parse((await run(process.execPath, ['scripts/deploy-records.mjs'], { env })).stdout).dryRun, true);
        await tx(controller.sendTransaction({ to: wallet.address, value: parseEther('1') })); env.CHAIN_SEND = '1';
        await run(process.execPath, ['scripts/deploy-records.mjs'], { env });
        const first = JSON.parse(fs.readFileSync(env.CHAIN_RECEIPT_FILE));
        assert.equal(first.status, 'confirmed');
        await run(process.execPath, ['scripts/deploy-records.mjs', '--resume'], { env });
        assert.equal(JSON.parse(fs.readFileSync(env.CHAIN_RECEIPT_FILE)).transactionHash, first.transactionHash);
      } finally { fs.rmSync(dir, { recursive: true, force: true }); }
    });
    await t.test('control handover requires the recipient; namespace separation prevents cross-company approvals', async () => {
      await tx(registry.proposeController(1, na));
      await fail(registry.connect(stranger).acceptController(1));
      assert.equal((await registry.organizations(1)).controller, ca);
      await tx(registry.connect(replacement).acceptController(1));
      await fail(registry.setPolicy(1, [aa], 1));
      await tx(registry.connect(stranger).createOrganization(id('another identity'), [aa], 1));
      await tx(registry.connect(stranger).append(2, key, 0, 0, id('v1-0'), false));
      const original = await registry.records(1, key, 1), another = await registry.records(2, key, 1);
      assert.notEqual(original.recordHash, another.recordHash);
      await fail(registry.connect(alice).attest(2, key, 1, original.recordHash, true));
    });
  } finally { rpc.destroy(); node.kill('SIGTERM'); }
});
