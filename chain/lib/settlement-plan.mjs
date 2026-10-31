import { Contract, keccak256 } from 'ethers';

/** Propose only deterministic timeout exits; never approve, arbitrate, fund, sign terms or withdraw. */
export async function planSettlements(provider, manifest, abi, { first = 1n, limit = 100 } = {}) {
  if (!Number.isInteger(limit) || limit < 1 || limit > 1000 || BigInt(first) < 1n) throw new Error('Invalid scan bounds');
  if ((await provider.getNetwork()).chainId !== BigInt(manifest.chainId)) throw new Error('Wrong chain');
  const head = Number(BigInt(await provider.send('eth_blockNumber', [])));
  const height = head - manifest.confirmations + 1;
  if (height < manifest.deploymentBlock) throw new Error('Deployment not confirmed');
  const block = await provider.getBlock(height);
  if (!block || keccak256(await provider.getCode(manifest.address, height)) !== manifest.runtimeCodeHash) throw new Error('Deployment mismatch');
  const c = new Contract(manifest.address, abi, provider), tag = { blockTag: height };
  const next = await c.nextId(tag), end = BigInt(first) + BigInt(limit) < next ? BigInt(first) + BigInt(limit) : next;
  const actions = [];
  for (let id = BigInt(first); id < end; id++) {
    const j = await c.getJob(id, tag); let method;
    if ((j.state === 1n || j.state === 2n) && BigInt(block.timestamp) > j.terms.fundingDeadline) method = 'closeUnfunded';
    if (j.state === 3n) {
      const m = await c.milestones(id, j.current, tag), now = BigInt(block.timestamp);
      if (m.stage === 0n && now > m.due) method = 'refundOverdue';
      else if (m.stage === 1n && now > m.reviewDeadline) method = 'releaseAfterReview';
      else if (m.stage === 2n && now > m.arbitrationDeadline) method = 'resolveAfterTimeout';
    }
    if (method) actions.push({ jobId: id.toString(), revision: j.revision.toString(), method,
      to: manifest.address, data: c.interface.encodeFunctionData(method, [id]), value: '0' });
  }
  if ((await provider.getBlock(height))?.hash !== block.hash) throw new Error('Reorg while planning');
  return { chainId: manifest.chainId, contract: manifest.address, blockNumber: height, blockHash: block.hash,
    actions, nextCursor: end < next ? end.toString() : null,
    note: 'Unsigned candidates only. Re-read state and simulate against latest before broadcasting; no automatic legal or discretionary decisions.' };
}
