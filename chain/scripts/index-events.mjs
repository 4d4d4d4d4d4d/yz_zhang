import fs from 'node:fs';
import path from 'node:path';
import { JsonRpcProvider } from 'ethers';
import { EventIndex } from '../lib/event-index.mjs';
import { loadArtifact } from './artifact.mjs';
const [manifestFile, databaseFile, type = 'TaskEscrow'] = process.argv.slice(2);
if (!manifestFile || !databaseFile || !['TaskEscrow', 'BusinessRecords'].includes(type)) throw new Error('Usage: node scripts/index-events.mjs MANIFEST DATABASE [TaskEscrow|BusinessRecords] [--watch|--export]');
const manifest = JSON.parse(fs.readFileSync(manifestFile));
fs.mkdirSync(path.dirname(path.resolve(databaseFile)), { recursive: true, mode: 0o700 });
const index = new EventIndex(databaseFile, manifest, loadArtifact(type).abi);
fs.chmodSync(databaseFile, 0o600);
const provider = new JsonRpcProvider(process.env.CHAIN_RPC_URL || manifest.rpcUrl, undefined, { cacheTimeout: -1 });
function publishMetrics(healthy, result = index.status()) {
  const target = process.env.CHAIN_INDEX_METRICS;
  if (!target) return;
  const last = result.lastSuccessAt ? Date.parse(result.lastSuccessAt) / 1000 : 0;
  const labels = `{contract_type="${type}"}`;
  const lines = [
    `opc_chain_index_healthy${labels} ${healthy ? 1 : 0}`,
    `opc_chain_index_last_success_seconds${labels} ${last}`,
    `opc_chain_index_height${labels} ${result.indexedBlock}`,
    `opc_chain_index_lag_blocks${labels} ${result.lagBlocks ?? 0}`,
  ];
  fs.writeFileSync(target + '.tmp', lines.join('\n') + '\n', { mode: 0o600 });
  fs.renameSync(target + '.tmp', target);
}
let stopped = false;
process.on('SIGTERM', () => { stopped = true; }); process.on('SIGINT', () => { stopped = true; });
try {
  if (process.argv.includes('--export')) {
    let synced; do { synced = await index.sync(provider); } while (synced.lagBlocks > 0);
    const events = index.events({ afterBlock: Number(process.env.AFTER_BLOCK ?? -1), afterLogIndex: Number(process.env.AFTER_LOG_INDEX ?? Number.MAX_SAFE_INTEGER), limit: Number(process.env.EVENT_LIMIT || 1000) });
    const last = events.at(-1);
    console.log(JSON.stringify({ deployment: { chainId: manifest.chainId, address: manifest.address },
    ...index.status(), events, nextCursor: last ? { afterBlock: last.block_number, afterLogIndex: last.log_index } : null,
    note: 'Bounded export; events may include public wallet addresses. Reconcile branch before evidentiary use.' }, null, 2));
  } else {
    do {
      try {
        const result = await index.sync(provider);
        console.log(JSON.stringify({ status: 'ok', type, ...result }));
        publishMetrics(true, result);
        if (process.env.CHAIN_INDEX_BACKUP && result.lagBlocks === 0) {
          const target = `${process.env.CHAIN_INDEX_BACKUP}.${result.indexedBlock}.${result.blockHash.slice(2,10)}.sqlite`;
          if (!fs.existsSync(target)) index.backup(target);
        }
        if (result.lagBlocks > 0) continue;
        if (!process.argv.includes('--watch')) break;
      } catch {
        publishMetrics(false);
        console.error(JSON.stringify({ status: 'error', type, note: 'Index update failed; retained prior committed state. Inspect RPC/deployment and retry.' }));
        if (!process.argv.includes('--watch')) { process.exitCode = 1; break; }
      }
      for (let i = 0; i < 15 && !stopped; i++) await new Promise(r => setTimeout(r, 1000));
    } while (!stopped);
  }
} finally { index.close(); provider.destroy(); }
