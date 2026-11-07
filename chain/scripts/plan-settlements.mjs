import fs from 'node:fs';
import { JsonRpcProvider } from 'ethers';
import { loadArtifact } from './artifact.mjs';
import { planSettlements } from '../lib/settlement-plan.mjs';
if (!process.argv[2]) throw new Error('Usage: node scripts/plan-settlements.mjs MANIFEST [FIRST_ID] [LIMIT]');
const manifest = JSON.parse(fs.readFileSync(process.argv[2]));
const p = new JsonRpcProvider(process.env.CHAIN_RPC_URL || manifest.rpcUrl, undefined, { cacheTimeout: -1 });
try { console.log(JSON.stringify(await planSettlements(p, manifest, loadArtifact('TaskEscrow').abi,
  { first: BigInt(process.argv[3] || 1), limit: Number(process.argv[4] || 100) }), null, 2)); }
finally { p.destroy(); }
