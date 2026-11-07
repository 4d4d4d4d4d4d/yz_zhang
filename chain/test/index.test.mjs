import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { JsonRpcProvider, ContractFactory, id, keccak256 } from 'ethers';
import { compile } from '../scripts/compile.mjs';
import { EventIndex } from '../lib/event-index.mjs';

test('durable event index: restart, duplicate polling, confirmed depth, reorg, atomic failure and backup', async () => {
  const child = spawn('node_modules/node/bin/node', ['node_modules/hardhat/dist/src/cli.js','node','--hostname','127.0.0.1','--port','18549'], { stdio:'ignore' });
  const p = new JsonRpcProvider('http://127.0.0.1:18549', 31337, { staticNetwork:true, cacheTimeout:-1 }); p.pollingInterval=25;
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'opc-event-index-')); let index;
  try {
    let ready=false; for(let i=0;i<80;i++) { try { await p.getBlockNumber(); ready=true;break; } catch { await delay(200); } } assert.ok(ready);
    const owner=await p.getSigner(0), a=compile('BusinessRecords');
    const c=await new ContractFactory(a.abi,a.bytecode,owner).deploy();await c.waitForDeployment();
    const manifest={chainId:31337,address:await c.getAddress(),runtimeCodeHash:keccak256(await p.getCode(await c.getAddress())),confirmations:2,deploymentBlock:(await c.deploymentTransaction().wait()).blockNumber};
    const file=path.join(dir,'events.sqlite'); index=new EventIndex(file,manifest,a.abi);
    await p.send('evm_mine',[]); await index.sync(p);
    await (await c.createOrganization(id('identity'),[await owner.getAddress()],1)).wait();
    assert.equal((await index.sync(p)).added,0,'unconfirmed events excluded');
    await p.send('evm_mine',[]); await index.sync(p);
    assert.equal(index.events().length,2);
    const page = index.events({ limit:1 })[0];
    assert.equal(index.events({afterBlock:page.block_number,afterLogIndex:page.log_index,limit:1})[0].event_name, 'PolicyChanged', 'pagination never skips a second event in the same block');
    assert.equal((await index.sync(p)).added,0);
    const snapshot=await p.send('evm_snapshot',[]);
    await (await c.append(1,id('record'),0,0,id('old branch'),false)).wait();await p.send('evm_mine',[]);
    await index.sync(p);assert.equal(index.events().length,3);
    index.close();index=new EventIndex(file,manifest,a.abi);assert.equal(index.events().length,3);
    await p.send('evm_revert',[snapshot]);
    await (await c.append(1,id('record'),0,0,id('replacement branch'),false)).wait();await p.send('evm_mine',[]);
    const result=await index.sync(p);assert.ok(result.rolledBack>0);
    assert.equal(index.events().length,3);assert.equal(index.events().at(-1).payload.commitment,id('replacement branch'));
    const before=index.status();
    await (await c.append(1,id('record'),1,0,id('next'),true)).wait();await p.send('evm_mine',[]);
    const broken={getNetwork:()=>p.getNetwork(),send:(...args)=>p.send(...args),getLogs:async()=>{throw new Error('RPC failure');}};
    await assert.rejects(index.sync(broken));assert.deepEqual(index.status(),before);
    await index.sync(p);const backup=path.join(dir,'backup.sqlite');index.backup(backup);
    const restored=new EventIndex(backup,manifest,a.abi);assert.equal(restored.events().length,4);restored.close();
    assert.throws(()=>new EventIndex(file,{...manifest,confirmations:3},a.abi),/different deployment/);
    await assert.rejects(index.sync({getNetwork:async()=>({chainId:1n})}),/Wrong RPC chain/);
  } finally {index?.close();p.destroy();child.kill('SIGTERM');fs.rmSync(dir,{recursive:true,force:true});}
});
