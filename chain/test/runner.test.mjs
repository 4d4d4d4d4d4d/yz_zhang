import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { JsonRpcProvider, ContractFactory, Wallet, parseEther, parseUnits, id, keccak256 } from 'ethers';
import { compile } from '../scripts/compile.mjs';
import { planSettlements } from '../lib/settlement-plan.mjs';
import { SettlementRunner } from '../lib/settlement-runner.mjs';

test('timeout runner: canonical eligibility, gas caps, durable recovery and no discretionary actions', async () => {
  const child=spawn('node_modules/node/bin/node',['node_modules/hardhat/dist/src/cli.js','node','--hostname','127.0.0.1','--port','18550'],{stdio:'ignore'});
  const p=new JsonRpcProvider('http://127.0.0.1:18550',31337,{staticNetwork:true,cacheTimeout:-1});p.pollingInterval=25;
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'opc-keeper-'));let runner;
  try {
    let ready=false;for(let i=0;i<80;i++){try{await p.getBlockNumber();ready=true;break;}catch{await delay(200);}}assert.ok(ready);
    const [owner,executor,arb]=await Promise.all([0,1,2].map(i=>p.getSigner(i)));
    const ta=compile('TestToken','test/TestToken.sol'),ea=compile('TaskEscrow');
    const token=await new ContractFactory(ta.abi,ta.bytecode,owner).deploy();await token.waitForDeployment();
    const c=await new ContractFactory(ea.abi,ea.bytecode,owner).deploy(await owner.getAddress(),await token.getAddress(),await arb.getAddress(),250);await c.waitForDeployment();
    const m={chainId:31337,address:await c.getAddress(),runtimeCodeHash:keccak256(await p.getCode(await c.getAddress())),confirmations:1,deploymentBlock:(await c.deploymentTransaction().wait()).blockNumber};
    const tx=async p=>(await p).wait();const now=Number((await p.getBlock('latest')).timestamp);
    await tx(c.create({executor:await executor.getAddress(),arbitrator:await arb.getAddress(),agreementHash:id('terms'),platformRef:id('task'),fundingDeadline:now+100,reviewPeriod:3600,arbitrationPeriod:86400,timeoutExecutorBps:5000},[10000],[now+10000]));
    await tx(c.connect(executor).accept(1,(await c.getJob(1)).termsHash));await tx(token.mint(await owner.getAddress(),10000));await tx(token.approve(await c.getAddress(),10000));await tx(c.fund(1));
    await tx(c.connect(executor).deliver(1,id('work')));
    assert.deepEqual((await planSettlements(p,m,ea.abi)).actions,[],'no early release');
    await p.send('evm_setNextBlockTimestamp',[Number((await c.milestones(1,0)).reviewDeadline)+1]);await p.send('evm_mine',[]);
    const plan=await planSettlements(p,m,ea.abi);assert.equal(plan.actions[0].method,'releaseAfterReview');
    const wallet=Wallet.createRandom().connect(p);await tx(owner.sendTransaction({to:wallet.address,value:parseEther('1')}));
    const file=path.join(dir,'journal.sqlite');runner=new SettlementRunner(file);
    const limits={maxFeePerGas:parseUnits('100','gwei'),maxTransactionFee:parseEther('0.02')};
    await assert.rejects(runner.run(p,wallet,m,ea.abi,{...plan.actions[0],method:'approve'},limits),/stale or unauthorized/);
    await assert.rejects(runner.run(p,wallet,m,ea.abi,plan.actions[0],{...limits,maxTransactionFee:1n}),/budget/);
    const offline={call:(...a)=>p.call(...a),getNetwork:()=>p.getNetwork(),getCode:(...a)=>p.getCode(...a),send:(...a)=>p.send(...a),getBlock:(...a)=>p.getBlock(...a),getFeeData:()=>p.getFeeData(),getBalance:(...a)=>p.getBalance(...a),getTransactionReceipt:(...a)=>p.getTransactionReceipt(...a),getTransaction:(...a)=>p.getTransaction(...a),broadcastTransaction:async()=>{throw new Error('connection lost before broadcast');}};
    await assert.rejects(runner.run(offline,wallet,m,ea.abi,plan.actions[0],limits),/connection lost/);
    const pending=runner.db.prepare("SELECT * FROM attempts WHERE status='pending'").get();assert.ok(pending.raw);assert.equal((await c.getJob(1)).state,3n);
    runner.close();runner=new SettlementRunner(file);
    const sent=await runner.run(p,wallet,m,ea.abi,undefined,limits);assert.equal(sent.hash,pending.hash);
    await p.waitForTransaction(sent.hash,1);
    const confirmed=await runner.run(p,wallet,m,ea.abi,undefined,limits);assert.equal(confirmed.status,'confirmed');assert.equal(confirmed.hash,pending.hash);
    assert.equal((await c.getJob(1)).state,4n);assert.equal(await c.credits(await executor.getAddress()),9750n);
    assert.equal(await token.balanceOf(wallet.address),0n,'keeper never receives customer funds');
    assert.equal((await runner.run(p,wallet,m,ea.abi,undefined,limits)).status,'idle');
    assert.equal(runner.db.prepare('SELECT COUNT(*) AS n FROM attempts').get().n,1);
    await assert.rejects(runner.run(p,Wallet.createRandom().connect(p),m,ea.abi,undefined,limits),/another chain/);
  } finally {runner?.close();p.destroy();child.kill('SIGTERM');fs.rmSync(dir,{recursive:true,force:true});}
});
