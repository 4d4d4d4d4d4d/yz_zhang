// LOCAL TEST CHAIN ONLY. Restart resets all state; public Hardhat keys must never hold real assets.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import { setTimeout as delay } from 'node:timers/promises';
import { JsonRpcProvider, ContractFactory, keccak256, parseEther, id } from 'ethers';
import { compile } from './compile.mjs';
import { seedRecords } from './seed-records.mjs';
const port = 18547;
// Refuse to reuse an unrelated node on the same port.
const probe = net.createServer();
await new Promise((resolve, reject) => { probe.once('error', reject); probe.listen(port, '127.0.0.1', resolve); });
await new Promise(resolve => probe.close(resolve));
const manifestPath = new URL('../../web/public/escrow-deployment.json', import.meta.url);
if (fs.existsSync(manifestPath)) {
  const existing = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  if (existing.chainId !== 31337 || existing.testOnly !== true || existing.rpcUrl !== `http://127.0.0.1:${port}`) throw new Error('Refusing to overwrite non-demo deployment');
}
const node = spawn('node_modules/node/bin/node', ['node_modules/hardhat/dist/src/cli.js', 'node', '--hostname', '127.0.0.1', '--port', String(port)], { stdio: 'ignore' });
const rpc = new JsonRpcProvider(`http://127.0.0.1:${port}`, 31337, { staticNetwork: true, cacheTimeout: -1 });
rpc.pollingInterval = 30;
let stopped = false;
const stop = () => { if (stopped) return; stopped = true; rpc.destroy(); node.kill('SIGTERM'); };
process.on('SIGINT', stop); process.on('SIGTERM', stop);
node.once('exit', () => { stop(); process.exitCode = 1; });
try {
  let ready = false;
  for (let i = 0; i < 100; i++) { if (node.exitCode !== null) break; try { await rpc.getBlockNumber(); ready = true; break; } catch { await delay(200); } }
  if (!ready || (await rpc.getNetwork()).chainId !== 31337n || !(await rpc.send('web3_clientVersion', [])).includes('Hardhat')) throw new Error('Demo EVM failed to start');
  const [owner, requester, executor, arb, fee] = await Promise.all([0, 1, 2, 3, 6].map(i => rpc.getSigner(i)));
  const ta = compile('TestToken', 'test/TestToken.sol'), ca = compile('TaskEscrow');
  const token = await new ContractFactory(ta.abi, ta.bytecode, owner).deploy(); await token.waitForDeployment();
  const escrow = await new ContractFactory(ca.abi, ca.bytecode, owner).deploy(await owner.getAddress(), await token.getAddress(), await fee.getAddress(), 250);
  await escrow.waitForDeployment();
  await (await token.mint(await requester.getAddress(), parseEther('10000'))).wait();
  const now = Number((await rpc.getBlock('latest')).timestamp);
  await (await escrow.connect(requester).create({ executor: await executor.getAddress(), arbitrator: await arb.getAddress(),
    agreementHash: id('OPC local demo agreement v1'), platformRef: id('DEMO-ONLY-001'), fundingDeadline: now + 7 * 86400,
    reviewPeriod: 3600, arbitrationPeriod: 86400, timeoutExecutorBps: 5000 }, [parseEther('100'), parseEther('200')], [now + 14 * 86400, now + 21 * 86400])).wait();
  await (await escrow.connect(executor).accept(1, (await escrow.getJob(1)).termsHash)).wait();
  await (await token.connect(requester).approve(await escrow.getAddress(), parseEther('300'))).wait();
  await (await escrow.connect(requester).fund(1)).wait();
  const manifest = { chainId: 31337, name: 'OPC 本地测试链', rpcUrl: `http://127.0.0.1:${port}`, address: await escrow.getAddress(),
    token: await token.getAddress(), runtimeCodeHash: keccak256(await rpc.getCode(await escrow.getAddress())), tokenSymbol: 'DEMO', tokenDecimals: 18,
    feeBps: 250, feeRecipient: await fee.getAddress(), confirmations: 1, testOnly: true,
    deploymentBlock: (await escrow.deploymentTransaction().wait()).blockNumber };
  fs.writeFileSync(new URL('../../web/public/escrow-deployment.json.tmp', import.meta.url), JSON.stringify(manifest, null, 2) + '\n');
  fs.renameSync(new URL('../../web/public/escrow-deployment.json.tmp', import.meta.url), manifestPath);
  await seedRecords(rpc);
  console.log('Demo ready: http://127.0.0.1:5173/chain?id=1 (300 DEMO escrowed; restart resets demo state)');
  console.log(JSON.stringify({ requester: await requester.getAddress(), executor: await executor.getAddress(), arbitrator: await arb.getAddress() }));
} catch (error) { console.error(error.message); stop(); process.exitCode = 1; }
