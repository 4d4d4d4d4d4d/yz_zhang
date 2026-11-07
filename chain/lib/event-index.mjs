import { DatabaseSync } from 'node:sqlite';
import { Interface, keccak256, getAddress } from 'ethers';

/** Rebuildable event index, never a second source of money or legal ownership. */
export class EventIndex {
  constructor(filename, manifest, abi) {
    if (!Number.isSafeInteger(manifest.chainId) || manifest.chainId < 1 || !Number.isSafeInteger(manifest.deploymentBlock) || manifest.deploymentBlock < 0
        || !Number.isInteger(manifest.confirmations) || manifest.confirmations < 1 || manifest.confirmations > 100
        || !/^0x[0-9a-f]{64}$/i.test(manifest.runtimeCodeHash)) throw new Error('Invalid index manifest');
    this.manifest = { ...manifest, address: getAddress(manifest.address) }; this.abi = new Interface(abi);
    this.db = new DatabaseSync(filename);
    this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=1000;
      CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS checkpoints (height INTEGER PRIMARY KEY, hash TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS events (block_number INTEGER NOT NULL, block_hash TEXT NOT NULL,
        transaction_hash TEXT NOT NULL, log_index INTEGER NOT NULL, event_name TEXT NOT NULL,
        topic1 TEXT, payload TEXT NOT NULL, PRIMARY KEY(transaction_hash, log_index));
      CREATE INDEX IF NOT EXISTS event_order ON events(block_number,log_index);
      CREATE INDEX IF NOT EXISTS event_topic ON events(topic1,block_number);`);
    const identity = JSON.stringify({ chainId: manifest.chainId, address: this.manifest.address, runtimeCodeHash: manifest.runtimeCodeHash,
      deploymentBlock: manifest.deploymentBlock, confirmations: manifest.confirmations });
    const existing = this.db.prepare("SELECT value FROM metadata WHERE key='identity'").get();
    if (existing && existing.value !== identity) { this.db.close(); throw new Error('Index belongs to a different deployment/finality policy'); }
    this.db.prepare("INSERT OR IGNORE INTO metadata VALUES('identity',?)").run(identity);
  }
  close() { this.db.close(); }
  status() {
    const tip = this.db.prepare('SELECT height,hash FROM checkpoints ORDER BY height DESC LIMIT 1').get();
    return { indexedBlock: tip?.height ?? this.manifest.deploymentBlock - 1, blockHash: tip?.hash ?? null,
      events: this.db.prepare('SELECT COUNT(*) AS n FROM events').get().n,
      lastSuccessAt: this.db.prepare("SELECT value FROM metadata WHERE key='lastSuccessAt'").get()?.value ?? null };
  }
  events({ afterBlock = -1, afterLogIndex = Number.MAX_SAFE_INTEGER, limit = 1000 } = {}) {
    if (!Number.isSafeInteger(afterBlock) || !Number.isSafeInteger(afterLogIndex) || !Number.isInteger(limit) || limit < 1 || limit > 10000) throw new Error('Invalid query bounds');
    return this.db.prepare('SELECT * FROM events WHERE block_number > ? OR (block_number = ? AND log_index > ?) ORDER BY block_number,log_index LIMIT ?').all(afterBlock, afterBlock, afterLogIndex, limit)
      .map(row => ({ ...row, payload: JSON.parse(row.payload) }));
  }
  async sync(provider, { batchSize = 250 } = {}) {
    if (!Number.isInteger(batchSize) || batchSize < 1 || batchSize > 2000) throw new Error('Invalid batch size');
    if ((await provider.getNetwork()).chainId !== BigInt(this.manifest.chainId)) throw new Error('Wrong RPC chain');
    // Bypass ethers short-lived block-number cache during reorg recovery.
    const head = Number(BigInt(await provider.send('eth_blockNumber', [])));
    const confirmed = head - this.manifest.confirmations + 1;
    const block = async n => provider.send('eth_getBlockByNumber', ['0x' + n.toString(16), false]);
    this.db.exec('BEGIN IMMEDIATE'); // Serializes writers through fetch+commit; process crashes roll back atomically.
    try {
      let rolledBack = 0;
      let checkpoint = this.db.prepare('SELECT height,hash FROM checkpoints ORDER BY height DESC LIMIT 1').get();
      while (checkpoint) {
        const canonical = checkpoint.height <= confirmed ? await block(checkpoint.height) : null;
        if (canonical && canonical.hash === checkpoint.hash) break;
        this.db.prepare('DELETE FROM checkpoints WHERE height=?').run(checkpoint.height); rolledBack++;
        checkpoint = this.db.prepare('SELECT height,hash FROM checkpoints ORDER BY height DESC LIMIT 1').get();
      }
      const previous = checkpoint?.height ?? this.manifest.deploymentBlock - 1;
      this.db.prepare('DELETE FROM events WHERE block_number > ?').run(previous);
      if (confirmed < this.manifest.deploymentBlock) throw new Error('Deployment is not sufficiently confirmed');
      const code = await provider.send('eth_getCode', [this.manifest.address, '0x' + confirmed.toString(16)]);
      if (code === '0x' || keccak256(code) !== this.manifest.runtimeCodeHash) throw new Error('Runtime code mismatch');
      const from = previous + 1, to = Math.min(confirmed, from + batchSize - 1);
      let added = 0;
      if (from <= to) {
        const before = await block(to); if (!before) throw new Error('Missing canonical block');
        const logs = await provider.getLogs({ address: this.manifest.address, fromBlock: from, toBlock: to });
        const hashes = new Map();
        for (const log of logs) {
          if (log.removed || log.blockNumber < from || log.blockNumber > to || getAddress(log.address) !== this.manifest.address) throw new Error('Invalid RPC event');
          if (!hashes.has(log.blockNumber)) hashes.set(log.blockNumber, (await block(log.blockNumber))?.hash);
          if (hashes.get(log.blockNumber) !== log.blockHash) throw new Error('Event is not on canonical branch');
          const parsed = this.abi.parseLog(log); if (!parsed) throw new Error('ABI cannot decode deployed event');
          const payload = Object.fromEntries(parsed.fragment.inputs.map((input, i) => [input.name || String(i), parsed.args[i]]));
          this.db.prepare('INSERT INTO events VALUES(?,?,?,?,?,?,?)').run(log.blockNumber, log.blockHash, log.transactionHash, log.index,
            parsed.name, log.topics[1] ?? null, JSON.stringify(payload, (_, v) => typeof v === 'bigint' ? v.toString() : v)); added++;
        }
        if ((await block(to))?.hash !== before.hash || (checkpoint && (await block(checkpoint.height))?.hash !== checkpoint.hash)) throw new Error('Chain reorganized during batch');
        this.db.prepare('INSERT INTO checkpoints VALUES(?,?)').run(to, before.hash);
      }
      this.db.prepare("INSERT INTO metadata VALUES('lastSuccessAt',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value").run(new Date().toISOString());
      this.db.exec('COMMIT');
      return { ...this.status(), confirmedBlock: confirmed, lagBlocks: confirmed - this.status().indexedBlock, added, rolledBack };
    } catch (error) { this.db.exec('ROLLBACK'); throw error; }
  }
  backup(filename) {
    // SQLite's transactionally consistent snapshot, including WAL content, instead of copying a live DB file.
    this.db.prepare('VACUUM INTO ?').run(filename);
  }
}
