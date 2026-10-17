import { DatabaseSync } from 'node:sqlite';
import { Contract, Transaction, keccak256 } from 'ethers';
import { planSettlements } from './settlement-plan.mjs';

/** Dedicated gas wallet, one pending transaction at a time, durable BEFORE broadcasting. */
export class SettlementRunner {
  constructor(filename) {
    this.db = new DatabaseSync(filename);
    this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=1000;
      CREATE TABLE IF NOT EXISTS identity (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS attempts (hash TEXT PRIMARY KEY, raw TEXT NOT NULL, job TEXT NOT NULL,
        method TEXT NOT NULL, revision TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);`);
  }
  close() { this.db.close(); }
  async run(provider, wallet, manifest, abi, candidate, { maxFeePerGas, maxTransactionFee }) {
    if (maxFeePerGas <= 0n || maxTransactionFee <= 0n) throw new Error('Explicit positive fee caps required');
    if ((await provider.getNetwork()).chainId !== BigInt(manifest.chainId)) throw new Error('Wrong chain');
    if (keccak256(await provider.getCode(manifest.address)) !== manifest.runtimeCodeHash) throw new Error('Code mismatch');
    const identity = JSON.stringify([manifest.chainId, manifest.address.toLowerCase(), wallet.address.toLowerCase()]);
    this.db.exec('BEGIN IMMEDIATE');
    let attempt;
    try {
      const saved = this.db.prepare('SELECT value FROM identity WHERE id=1').get();
      if (saved && saved.value !== identity) throw new Error('Journal belongs to another chain, contract or gas wallet');
      this.db.prepare('INSERT OR IGNORE INTO identity VALUES(1,?)').run(identity);
      attempt = this.db.prepare("SELECT * FROM attempts WHERE status='pending' LIMIT 1").get();
      if (!attempt) {
        if (!candidate) { this.db.exec('COMMIT'); return { status: 'idle' }; }
        // Recompute allowed action from a confirmed canonical block; caller cannot supply arbitrary calldata.
        const plan = await planSettlements(provider, manifest, abi, { first: BigInt(candidate.jobId), limit: 1 });
        const allowed = plan.actions.find(a => a.method === candidate.method && a.revision === candidate.revision);
        if (!allowed) throw new Error('Timeout candidate is stale or unauthorized');
        const c = new Contract(manifest.address, abi, wallet);
        if (String((await c.getJob(allowed.jobId)).revision) !== allowed.revision) throw new Error('Latest state changed since confirmation');
        await c.getFunction(allowed.method).staticCall(allowed.jobId);
        const estimated = await c.getFunction(allowed.method).estimateGas(allowed.jobId);
        const gasLimit = (estimated * 120n + 99n) / 100n;
        if (gasLimit > 1000000n) throw new Error('Gas limit exceeds keeper bound');
        const fees = await provider.getFeeData(), price = fees.maxFeePerGas ?? fees.gasPrice;
        if (!price || price > maxFeePerGas || price * gasLimit > maxTransactionFee) throw new Error('Gas budget exceeded');
        if (await provider.getBalance(wallet.address) < price * gasLimit) throw new Error('Insufficient gas balance');
        const request = await wallet.populateTransaction({ to: manifest.address, data: allowed.data, value: 0n, gasLimit,
          ...(fees.maxFeePerGas ? { type: 2, maxFeePerGas: price, maxPriorityFeePerGas: fees.maxPriorityFeePerGas ?? 0n } : { type: 0, gasPrice: price }) });
        const raw = await wallet.signTransaction(request), hash = keccak256(raw);
        this.db.prepare('INSERT INTO attempts VALUES(?,?,?,?,?,?,?)').run(hash, raw, allowed.jobId, allowed.method, allowed.revision, 'pending', new Date().toISOString());
        attempt = this.db.prepare('SELECT * FROM attempts WHERE hash=?').get(hash);
      }
      this.db.exec('COMMIT'); // The exact signed transaction is recoverable even if the very next instruction fails.
    } catch (error) { this.db.exec('ROLLBACK'); throw error; }
    const parsed = Transaction.from(attempt.raw);
    if (parsed.hash !== attempt.hash || parsed.chainId !== BigInt(manifest.chainId) || parsed.to?.toLowerCase() !== manifest.address.toLowerCase()
        || parsed.from?.toLowerCase() !== wallet.address.toLowerCase() || parsed.value !== 0n) throw new Error('Journal integrity error');
    const receipt = await provider.getTransactionReceipt(attempt.hash);
    if (receipt) {
      const canonical = await provider.getBlock(receipt.blockNumber);
      if (canonical?.hash !== receipt.blockHash) throw new Error('Receipt reorganized; retain pending transaction');
      if (await receipt.confirmations() < manifest.confirmations) return { status: 'pending', hash: attempt.hash };
      const status = receipt.status === 1 ? 'confirmed' : 'reverted';
      this.db.prepare('UPDATE attempts SET status=? WHERE hash=?').run(status, attempt.hash);
      return { status, hash: attempt.hash, jobId: attempt.job, method: attempt.method };
    }
    if (!await provider.getTransaction(attempt.hash)) await provider.broadcastTransaction(attempt.raw);
    return { status: 'pending', hash: attempt.hash, jobId: attempt.job, method: attempt.method };
  }
}
