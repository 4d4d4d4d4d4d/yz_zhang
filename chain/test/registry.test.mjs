import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';
import { JsonRpcProvider, ContractFactory, id } from 'ethers';
import { compile } from '../scripts/compile.mjs';

test('checkpoint authorization, continuity, immutability, pause and ownership recovery', async () => {
  const node = spawn('node_modules/node/bin/node', ['node_modules/hardhat/dist/src/cli.js', 'node', '--hostname', '127.0.0.1', '--port', '18545'], { stdio: 'ignore' });
  const rpc = new JsonRpcProvider('http://127.0.0.1:18545', 31337, { staticNetwork: true });
  try {
    let ready = false;
    for (let i = 0; i < 60; i++) {
      try { await rpc.getBlockNumber(); ready = true; break; } catch { await delay(250); }
    }
    assert.ok(ready, 'local EVM started');
    const owner = await rpc.getSigner(0), publisher = await rpc.getSigner(1), outsider = await rpc.getSigner(2);
    const artifact = compile();
    const registry = await new ContractFactory(artifact.abi, artifact.bytecode, owner).deploy(await owner.getAddress(), await publisher.getAddress());
    await registry.waitForDeployment();
    await assert.rejects(registry.connect(outsider).anchor(1, 5, id('first')));
    await assert.rejects(registry.connect(publisher).anchor(2, 5, id('first')));
    await (await registry.connect(publisher).anchor(1, 5, id('first'))).wait();
    assert.equal(await registry.lastSequence(), 5n);
    assert.equal((await registry.checkpoints(5)).digest, id('first'));
    await assert.rejects(registry.connect(publisher).anchor(1, 5, id('replacement')));
    await (await registry.setPaused(true)).wait();
    await assert.rejects(registry.connect(publisher).anchor(6, 9, id('second')));
    await (await registry.setPaused(false)).wait();
    await (await registry.connect(publisher).anchor(6, 9, id('second'), { gasLimit: 200000 })).wait();
    await assert.rejects(registry.connect(outsider).setPublisher(await outsider.getAddress()));
    await (await registry.transferOwnership(await outsider.getAddress())).wait();
    assert.equal(await registry.owner(), await owner.getAddress());
    await (await registry.connect(outsider).acceptOwnership()).wait();
    assert.equal(await registry.owner(), await outsider.getAddress());
    await assert.rejects(registry.connect(outsider).renounceOwnership());
    assert.equal((await registry.checkpoints(5)).digest, id('first'));
  } finally { rpc.destroy(); node.kill('SIGTERM'); }
});
