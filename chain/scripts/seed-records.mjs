// Synthetic business records, local Hardhat only. Does not encode a real company or execute legal transactions.
import fs from 'node:fs';
import { JsonRpcProvider, ContractFactory, id, keccak256 } from 'ethers';
import { compile } from './compile.mjs';
export async function seedRecords(rpc) {
  if ((await rpc.getNetwork()).chainId !== 31337n || !(await rpc.send('web3_clientVersion', [])).includes('Hardhat')) throw new Error('Local demo chain only');
  const target = new URL('../../web/public/business-records-deployment.json', import.meta.url);
  if (fs.existsSync(target)) {
    const existing = JSON.parse(fs.readFileSync(target, 'utf8'));
    if (existing.chainId !== 31337 || existing.testOnly !== true || existing.rpcUrl !== 'http://127.0.0.1:18547') throw new Error('Refusing to replace non-demo business records deployment');
    const code = await rpc.getCode(existing.address);
    if (code !== '0x' && keccak256(code) === existing.runtimeCodeHash) return existing;
  }
  const [owner, a, b] = await Promise.all([0, 1, 2].map(i => rpc.getSigner(i)));
  const artifact = compile('BusinessRecords');
  const c = await new ContractFactory(artifact.abi, artifact.bytecode, owner).deploy(); await c.waitForDeployment();
  await (await c.createOrganization(id('SYNTHETIC ORGANIZATION - NO REAL IDENTITY'), [await a.getAddress(), await b.getAddress()], 2)).wait();
  for (const [kind, key] of ['DEMO-EQUITY', 'DEMO-AGREEMENT', 'DEMO-LEGAL', 'DEMO-FINANCIAL'].entries()) {
    await (await c.append(1, id(key), 0, kind, id(`SYNTHETIC COMMITMENT ${key} v1 - NOT A REAL DOCUMENT`), false)).wait();
    const row = await c.records(1, id(key), 1);
    await (await c.connect(a).attest(1, id(key), 1, row.recordHash, true)).wait();
    await (await c.connect(b).attest(1, id(key), 1, row.recordHash, true)).wait();
  }
  await (await c.append(1, id('DEMO-EQUITY'), 1, 0, id('SYNTHETIC EQUITY CORRECTION v2'), true)).wait();
  const manifest = { chainId: 31337, name: 'OPC 本地测试链', rpcUrl: 'http://127.0.0.1:18547', address: await c.getAddress(),
    runtimeCodeHash: keccak256(await rpc.getCode(await c.getAddress())), confirmations: 1, testOnly: true,
    deploymentBlock: (await c.deploymentTransaction().wait()).blockNumber };
  fs.writeFileSync(target, JSON.stringify(manifest, null, 2) + '\n');
  return manifest;
}
if (process.argv[1] === new URL(import.meta.url).pathname) {
  const p = new JsonRpcProvider('http://127.0.0.1:18547', 31337, { staticNetwork: true, cacheTimeout: -1 }); p.pollingInterval = 25;
  try { console.log(JSON.stringify(await seedRecords(p))); } finally { p.destroy(); }
}
