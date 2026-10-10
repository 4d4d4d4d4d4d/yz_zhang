// No broadcast without CHAIN_SEND=1 and explicit fee ceilings. Never auto-approve work or arbitrate.
import fs from 'node:fs';
import { JsonRpcProvider, Wallet, parseUnits, parseEther } from 'ethers';
import { loadArtifact } from './artifact.mjs';
import { planSettlements } from '../lib/settlement-plan.mjs';
import { SettlementRunner } from '../lib/settlement-runner.mjs';
const manifest = JSON.parse(fs.readFileSync(process.argv[2]));
const provider = new JsonRpcProvider(process.env.CHAIN_RPC_URL || manifest.rpcUrl, undefined, { cacheTimeout: -1 });
let runner;
try {
  const abi = loadArtifact('TaskEscrow').abi;
  const plan = await planSettlements(provider, manifest, abi, { first: BigInt(process.env.KEEPER_FIRST_ID || 1), limit: Number(process.env.KEEPER_SCAN_LIMIT || 100) });
  if (process.env.CHAIN_SEND !== '1') console.log(JSON.stringify({ dryRun: true, ...plan }, null, 2));
  else {
    for (const name of ['CHAIN_KEY_FILE', 'KEEPER_JOURNAL', 'KEEPER_MAX_GWEI', 'KEEPER_MAX_TX_ETH']) if (!process.env[name]) throw new Error(`Missing ${name}`);
    const wallet = new Wallet(fs.readFileSync(process.env.CHAIN_KEY_FILE, 'utf8').trim(), provider);
    runner = new SettlementRunner(process.env.KEEPER_JOURNAL); fs.chmodSync(process.env.KEEPER_JOURNAL, 0o600);
    console.log(JSON.stringify(await runner.run(provider, wallet, manifest, abi, plan.actions[0], {
      maxFeePerGas: parseUnits(process.env.KEEPER_MAX_GWEI, 'gwei'), maxTransactionFee: parseEther(process.env.KEEPER_MAX_TX_ETH),
    })));
  }
} finally { runner?.close(); provider.destroy(); }
