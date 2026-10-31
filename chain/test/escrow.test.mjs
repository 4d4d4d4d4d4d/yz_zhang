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

test('TaskEscrow: real EVM lifecycle and adversarial transitions', async t => {
  const node = spawn('node_modules/node/bin/node', ['node_modules/hardhat/dist/src/cli.js', 'node', '--hostname', '127.0.0.1', '--port', '18546'], { stdio: 'ignore' });
  const rpc = new JsonRpcProvider('http://127.0.0.1:18546', 31337, { staticNetwork: true, cacheTimeout: -1 });
  rpc.pollingInterval = 25;
  try {
    let ready = false;
    for (let i = 0; i < 80; i++) {
      try { await rpc.getBlockNumber(); ready = true; break; } catch { await delay(200); }
    }
    assert.ok(ready);
    const [owner, requester, executor, arb, machine, other, fee] = await Promise.all(Array.from({ length: 7 }, (_, i) => rpc.getSigner(i)));
    const addresses = await Promise.all([owner, requester, executor, arb, machine, other, fee].map(s => s.getAddress()));
    const [oa, ra, ea, aa, ma, _xa, fa] = addresses;
    const ta = compile('TestToken', 'test/TestToken.sol'), ca = compile('TaskEscrow');
    assert.ok((ca.deployedBytecode.length - 2) / 2 < 24576, 'deployable EIP-170 bytecode size');
    const token = await new ContractFactory(ta.abi, ta.bytecode, owner).deploy(); await token.waitForDeployment();
    const escrow = await new ContractFactory(ca.abi, ca.bytecode, owner).deploy(oa, await token.getAddress(), fa, 250); await escrow.waitForDeployment();
    const address = await escrow.getAddress();
    const now = async () => Number((await rpc.getBlock('latest')).timestamp);
    const jump = async timestamp => { await rpc.send('evm_setNextBlockTimestamp', [timestamp]); await rpc.send('evm_mine', []); };
    const tx = async p => (await p).wait();
    const rejected = async p => assert.rejects(async () => tx(p));
    async function invariant() {
      const liability = await escrow.totalEscrowed() + await escrow.totalCredits();
      assert.equal(await token.balanceOf(address), liability, 'every deposited token accounted for');
      let credits = 0n; for (const a of addresses) credits += await escrow.credits(a);
      assert.equal(credits, await escrow.totalCredits());
    }
    async function create(amounts = [10000n, 20000n], overrides = {}) {
      const ts = await now(), jobId = await escrow.nextId();
      const terms = { executor: ea, arbitrator: aa, agreementHash: id('signed document'), platformRef: id(`platform-task-${jobId}`),
        fundingDeadline: ts + 3600, reviewPeriod: 3600, arbitrationPeriod: 86400, timeoutExecutorBps: 5000, ...overrides };
      const dues = amounts.map((_, i) => ts + 86400 * (i + 1));
      await tx(escrow.connect(requester).create(terms, amounts, dues));
      return { jobId, terms, dues };
    }
    async function funded(amounts) {
      const j = await create(amounts), job = await escrow.getJob(j.jobId);
      await tx(escrow.connect(executor).accept(j.jobId, job.termsHash));
      await tx(token.mint(ra, job.total)); await tx(token.connect(requester).approve(address, job.total));
      await tx(escrow.connect(requester).fund(j.jobId)); await invariant(); return j;
    }
    await t.test('acceptance binds terms, requester alone funds, exact amount and no double fund', async () => {
      const { jobId } = await create(); const j = await escrow.getJob(jobId);
      await rejected(escrow.connect(requester).fund(jobId));
      await rejected(escrow.connect(other).accept(jobId, j.termsHash));
      await rejected(escrow.connect(executor).accept(jobId, id('different terms')));
      await tx(escrow.connect(executor).accept(jobId, j.termsHash));
      await rejected(escrow.connect(requester).fund(jobId));
      await tx(token.mint(ra, j.total)); await tx(token.connect(requester).approve(address, j.total));
      await rejected(escrow.connect(other).fund(jobId));
      await tx(token.setTaxed(true)); await rejected(escrow.connect(requester).fund(jobId));
      assert.equal((await escrow.getJob(jobId)).remaining, 0n);
      await tx(token.setTaxed(false)); await tx(escrow.connect(requester).fund(jobId, { gasLimit: 250000 }));
      await rejected(escrow.connect(requester).fund(jobId)); await invariant();
    });
    await t.test('sequential delivery, review expiry, fees and pull withdrawal, paused exits work', async () => {
      const { jobId } = await funded();
      await rejected(escrow.connect(requester).approve(jobId));
      await rejected(escrow.connect(other).deliver(jobId, id('work')));
      await tx(escrow.connect(executor).deliver(jobId, id('work')));
      await rejected(escrow.connect(other).approve(jobId));
      await rejected(escrow.releaseAfterReview(jobId));
      await tx(escrow.setPaused(true));
      await rejected(create());
      await tx(escrow.connect(requester).approve(jobId));
      assert.equal(await escrow.credits(ea), 9750n); assert.equal(await escrow.credits(fa), 250n);
      await tx(escrow.connect(executor).deliver(jobId, id('second')));
      const m = await escrow.milestones(jobId, 1); await jump(Number(m.reviewDeadline) + 1);
      await tx(escrow.connect(other).releaseAfterReview(jobId));
      assert.equal((await escrow.getJob(jobId)).state, 4n);
      assert.equal(await escrow.credits(ea), 29250n);
      await tx(token.setBlocked(true)); await rejected(escrow.connect(executor).withdraw());
      assert.equal(await escrow.credits(ea), 29250n, 'failed payout preserves credit');
      await tx(token.setBlocked(false)); await tx(escrow.connect(executor).withdraw({ gasLimit: 150000 }));
      assert.equal(await token.balanceOf(ea), 29250n);
      await rejected(escrow.connect(executor).withdraw());
      await tx(escrow.setPaused(false)); await invariant();
    });
    await t.test('disputes freeze release; only agreed arb can split, timeout deterministically exits', async () => {
      const { jobId } = await funded([10000n]);
      await tx(escrow.connect(executor).deliver(jobId, id('evidence')));
      await tx(escrow.connect(requester).dispute(jobId, id('objection')));
      await rejected(escrow.connect(requester).approve(jobId)); await rejected(escrow.releaseAfterReview(jobId));
      await rejected(escrow.refundOverdue(jobId));
      await rejected(escrow.connect(owner).resolve(jobId, 5000, id('decision')));
      await rejected(escrow.connect(arb).resolve(jobId, 10001, id('decision')));
      const before = await escrow.credits(ra);
      await tx(escrow.connect(arb).resolve(jobId, 4000, id('decision')));
      assert.equal(await escrow.credits(ra) - before, 6000n);
      await rejected(escrow.connect(arb).resolve(jobId, 4000, id('again')));
      const timeout = await funded([10001n]);
      await tx(escrow.connect(executor).deliver(timeout.jobId, id('evidence')));
      await tx(escrow.connect(executor).dispute(timeout.jobId, id('objection')));
      await rejected(escrow.resolveAfterTimeout(timeout.jobId));
      const m = await escrow.milestones(timeout.jobId, 0); await jump(Number(m.arbitrationDeadline) + 1);
      await rejected(escrow.connect(arb).resolve(timeout.jobId, 1, id('late')));
      const rc = await escrow.credits(ra), ec = await escrow.credits(ea);
      await tx(escrow.connect(other).resolveAfterTimeout(timeout.jobId));
      assert.equal(await escrow.credits(ra) - rc, 5001n); assert.equal(await escrow.credits(ea) - ec, 4875n);
      await invariant();
    });
    await t.test('undelivered overdue work refunds remaining; submitted work cannot be clawed back', async () => {
      const { jobId, dues } = await funded();
      await rejected(escrow.refundOverdue(jobId));
      await jump(dues[0] + 1);
      await rejected(escrow.connect(executor).deliver(jobId, id('late')));
      const before = await escrow.credits(ra); await tx(escrow.connect(other).refundOverdue(jobId));
      assert.equal(await escrow.credits(ra) - before, 30000n);
      await rejected(escrow.refundOverdue(jobId)); await invariant();
    });
    await t.test('mutual cancellation cannot be self accepted, replayed or substituted', async () => {
      const { jobId } = await funded();
      await tx(escrow.connect(requester).proposeCancellation(jobId, 12000, await now() + 3600));
      const c = await escrow.cancellations(jobId);
      await rejected(escrow.connect(requester).acceptCancellation(jobId, c.revision, 12000));
      await rejected(escrow.connect(other).acceptCancellation(jobId, c.revision, 12000));
      await tx(escrow.connect(requester).proposeCancellation(jobId, 11000, await now() + 3600));
      await rejected(escrow.connect(executor).acceptCancellation(jobId, c.revision, 12000));
      let fresh = await escrow.cancellations(jobId);
      await tx(escrow.connect(executor).deliver(jobId, id('work')));
      await rejected(escrow.connect(executor).acceptCancellation(jobId, fresh.revision, 11000));
      await tx(escrow.connect(requester).proposeCancellation(jobId, 12000, await now() + 3600)); fresh = await escrow.cancellations(jobId);
      await rejected(escrow.connect(executor).acceptCancellation(jobId, fresh.revision, 11999));
      await tx(escrow.connect(executor).acceptCancellation(jobId, fresh.revision, 12000));
      await rejected(escrow.connect(executor).acceptCancellation(jobId, fresh.revision, 12000)); await invariant();
    });
    await t.test('machine delegation has expiry and revocation, no financial authority', async () => {
      const { jobId } = await funded();
      await rejected(escrow.connect(requester).setDelegate(jobId, ma, await now() + 500));
      await tx(escrow.connect(executor).setDelegate(jobId, ma, await now() + 500));
      await rejected(escrow.connect(machine).approve(jobId)); await rejected(escrow.connect(machine).dispute(jobId, id('bad')));
      await rejected(escrow.connect(machine).proposeCancellation(jobId, 30000, await now() + 500));
      await rejected(escrow.connect(machine).withdraw());
      await tx(escrow.connect(executor).setDelegate(jobId, ZeroAddress, 0));
      await rejected(escrow.connect(machine).deliver(jobId, id('work')));
      const expires = await now() + 50; await tx(escrow.connect(executor).setDelegate(jobId, ma, expires));
      await jump(expires + 1); await rejected(escrow.connect(machine).deliver(jobId, id('work')));
      await tx(escrow.connect(executor).setDelegate(jobId, ma, await now() + 500));
      await tx(escrow.connect(machine).deliver(jobId, id('work'), { gasLimit: 150000 })); await invariant();
    });
    await t.test('contract wallets participate without EOA assumptions; untrusted callers cannot impersonate the controller', async () => {
      const artifact = compile('ActorWallet', 'test/ActorWallet.sol');
      const actor = await new ContractFactory(artifact.abi, artifact.bytecode, executor).deploy(ea);
      await actor.waitForDeployment();
      const actorAddress = await actor.getAddress();
      const { jobId } = await create([10000n], { executor: actorAddress });
      const termsHash = (await escrow.getJob(jobId)).termsHash;
      const acceptData = escrow.interface.encodeFunctionData('accept', [jobId, termsHash]);
      await rejected(actor.connect(other).execute(address, acceptData));
      await tx(actor.execute(address, acceptData));
      await tx(token.mint(ra, 10000)); await tx(token.connect(requester).approve(address, 10000));
      await tx(escrow.connect(requester).fund(jobId));
      await tx(actor.execute(address, escrow.interface.encodeFunctionData('deliver', [jobId, id('contract wallet work')])));
      await tx(escrow.connect(requester).approve(jobId));
      assert.equal(await escrow.credits(actorAddress), 9750n);
      await tx(actor.execute(address, escrow.interface.encodeFunctionData('withdraw')));
      assert.equal(await token.balanceOf(actorAddress), 9750n); await invariant();
    });
    await t.test('deployment is dry-run by default; signed broadcast, resume and confirmed accounting are reproducible', async () => {
      const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'opc-escrow-deploy-'));
      const run = promisify(execFile);
      const deployer = Wallet.createRandom();
      const keyFile = path.join(dir, 'key');
      fs.writeFileSync(keyFile, deployer.privateKey, { mode: 0o600 });
      const receiptFile = path.join(dir, 'receipt.json'), manifestFile = path.join(dir, 'manifest.json');
      const env = { ...process.env, CHAIN_RPC_URL: 'http://127.0.0.1:18546', CHAIN_ID: '31337', CHAIN_OWNER: oa,
        ESCROW_TOKEN: await token.getAddress(), ESCROW_FEE_RECIPIENT: fa, ESCROW_FEE_BPS: '250', CHAIN_CONFIRMATIONS: '1',
        CHAIN_KEY_FILE: keyFile, CHAIN_RECEIPT_FILE: receiptFile, ESCROW_MANIFEST_FILE: manifestFile,
        ESCROW_PUBLIC_RPC_URL: 'http://127.0.0.1:18546', ESCROW_NETWORK_NAME: 'EVM integration test', ESCROW_TEST_ONLY: '1', CHAIN_SEND: '0' };
      try {
        const dry = await run(process.execPath, ['scripts/deploy-escrow.mjs'], { env });
        assert.equal(JSON.parse(dry.stdout).dryRun, true); assert.equal(fs.existsSync(receiptFile), false);
        await tx(owner.sendTransaction({ to: deployer.address, value: parseEther('1') }));
        env.CHAIN_SEND = '1';
        await run(process.execPath, ['scripts/deploy-escrow.mjs'], { env });
        const record = JSON.parse(fs.readFileSync(receiptFile)); assert.equal(record.status, 'confirmed');
        await run(process.execPath, ['scripts/deploy-escrow.mjs', '--resume'], { env });
        assert.equal(JSON.parse(fs.readFileSync(receiptFile)).transactionHash, record.transactionHash);
        await assert.rejects(run(process.execPath, ['scripts/deploy-escrow.mjs'], { env }));
        const audit = await run(process.execPath, ['scripts/audit-escrow.mjs', manifestFile], { env });
        assert.equal(JSON.parse(audit.stdout).valid, true);
        await assert.rejects(run(process.execPath, ['scripts/deploy-escrow.mjs', '--resume'], { env: { ...env, CHAIN_ID: '1' } }));
      } finally { fs.rmSync(dir, { recursive: true, force: true }); }
    });
    await t.test('funding expiry and offer cancellation leave no trapped funds', async () => {
      const { jobId, terms } = await create([10000n]);
      await rejected(escrow.connect(other).closeUnfunded(jobId));
      await jump(terms.fundingDeadline + 1);
      await rejected(escrow.connect(executor).accept(jobId, (await escrow.getJob(jobId)).termsHash));
      await tx(escrow.connect(other).closeUnfunded(jobId));
      const j = await create([10000n]);
      await tx(escrow.connect(requester).closeUnfunded(j.jobId));
      await rejected(escrow.connect(executor).accept(j.jobId, (await escrow.getJob(j.jobId)).termsHash));
      await rejected(escrow.connect(other).setPaused(true)); await rejected(escrow.renounceOwnership());
      await invariant();
    });
  } finally { rpc.destroy(); node.kill('SIGTERM'); }
});
