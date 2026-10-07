// Read-only reconciliation at a confirmed block. No wallet or signing key needed.
import fs from 'node:fs';
import { JsonRpcProvider, Contract, keccak256 } from 'ethers';
import { compile } from './compile.mjs';
const manifest = JSON.parse(fs.readFileSync(process.argv[2] || '../web/public/escrow-deployment.json', 'utf8'));
const provider = new JsonRpcProvider(process.env.CHAIN_RPC_URL || manifest.rpcUrl);
try {
  if ((await provider.getNetwork()).chainId !== BigInt(manifest.chainId)) throw new Error('Wrong chain');
  const height = await provider.getBlockNumber() - manifest.confirmations + 1;
  if (height < manifest.deploymentBlock) throw new Error('Deployment is not sufficiently confirmed');
  const before = await provider.getBlock(height);
  const tag = { blockTag: height };
  if (keccak256(await provider.getCode(manifest.address, height)) !== manifest.runtimeCodeHash) throw new Error('Runtime code mismatch');
  const escrow = new Contract(manifest.address, compile('TaskEscrow').abi, provider);
  const token = new Contract(manifest.token, ['function balanceOf(address) view returns(uint256)'], provider);
  if ((await escrow.token(tag)).toLowerCase() !== manifest.token.toLowerCase()) throw new Error('Token mismatch');
  const [balance, held, credits, nextId] = await Promise.all([token.balanceOf(manifest.address, tag), escrow.totalEscrowed(tag), escrow.totalCredits(tag), escrow.nextId(tag)]);
  let remaining = 0n;
  // Bounded sequential reads keep public RPC rate predictable; can resume by block externally.
  for (let i = 1n; i < nextId; i++) remaining += (await escrow.getJob(i, tag)).remaining;
  const after = await provider.getBlock(height);
  if (!before || !after || before.hash !== after.hash) throw new Error('Chain reorganized during audit; retry');
  const valid = balance >= held + credits && remaining === held;
  console.log(JSON.stringify({ valid, chainId: manifest.chainId, contract: manifest.address, blockNumber: height, blockHash: before.hash,
    balance: String(balance), escrowed: String(held), credits: String(credits), sumJobRemaining: String(remaining),
    surplus: String(balance - held - credits), jobs: String(nextId - 1n), note: 'Read-only accounting check; does not certify off-chain legal identity or token solvency.' }, null, 2));
  if (!valid) process.exitCode = 2;
} finally { provider.destroy(); }
