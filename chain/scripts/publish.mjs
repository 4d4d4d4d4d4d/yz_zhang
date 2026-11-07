// Only hashes leave the platform. A broadcast requires CHAIN_SEND=1 explicitly.
import { readFileSync, writeFileSync } from 'node:fs';
import { JsonRpcProvider, Wallet, Contract, ContractFactory, getAddress } from 'ethers';
import { compile } from './compile.mjs';
const required = name => { if (!process.env[name]) throw new Error(`Missing ${name}`); return process.env[name]; };
const rpc = new JsonRpcProvider(required('CHAIN_RPC_URL'));
try {
  const chainId = BigInt(required('CHAIN_ID'));
  if ((await rpc.getNetwork()).chainId !== chainId) throw new Error('Wrong network');
  const artifact = compile();
  if (process.argv.includes('--deploy')) {
    const owner = getAddress(required('CHAIN_OWNER'));
    const publisher = getAddress(required('CHAIN_PUBLISHER'));
    if (process.env.CHAIN_SEND !== '1') throw new Error('Deployment requires CHAIN_SEND=1');
    const wallet = new Wallet(readFileSync(required('CHAIN_KEY_FILE'), 'utf8').trim(), rpc);
    const contract = await new ContractFactory(artifact.abi, artifact.bytecode, wallet).deploy(owner, publisher);
    const receipt = await contract.deploymentTransaction().wait(Number(process.env.CHAIN_CONFIRMATIONS || 12));
    console.log(JSON.stringify({ address: await contract.getAddress(), chainId: String(chainId), transactionHash: receipt.hash }));
  } else {
    const address = getAddress(required('CHAIN_CONTRACT'));
    if (await rpc.getCode(address) === '0x') throw new Error('No deployed contract');
    const contract = new Contract(address, artifact.abi, rpc);
    const base = new URL(required('PLATFORM_API_BASE'));
    if (base.protocol !== 'https:' && !(base.protocol === 'http:' && ['localhost','127.0.0.1'].includes(base.hostname))) throw new Error('API must use HTTPS or loopback');
    const response = await fetch(new URL(base.toString().replace(/\/$/, '') + '/anchors/verify'), { signal: AbortSignal.timeout(30000), redirect: 'error' });
    if (!response.ok) throw new Error('Platform verification unavailable');
    const head = await response.json();
    if (head.valid !== true || !Number.isSafeInteger(head.total) || head.total < 0 || !/^[a-f0-9]{64}$/.test(head.head)) throw new Error('Invalid platform chain');
    const previous = await contract.lastSequence();
    const last = BigInt(head.total);
    if (last < previous) throw new Error('Platform history rolled back');
    if (last === previous) {
      if (last && (await contract.checkpoints(last)).digest !== '0x' + head.head) throw new Error('Checkpoint mismatch');
      console.log('Already anchored');
    } else {
      const plan = { chainId: String(chainId), address, first: String(previous + 1n), last: String(last), digest: '0x' + head.head };
      if (process.env.CHAIN_SEND !== '1') console.log(JSON.stringify({ dryRun: true, ...plan }));
      else {
        const wallet = new Wallet(readFileSync(required('CHAIN_KEY_FILE'), 'utf8').trim(), rpc);
        if ((await contract.publisher()).toLowerCase() !== wallet.address.toLowerCase()) throw new Error('Wrong publisher key');
        const out = required('CHAIN_RECEIPT_FILE');
        const tx = await contract.connect(wallet).anchor(previous + 1n, last, plan.digest);
        // Persist the hash before waiting so a timeout never causes a blind resend.
        writeFileSync(out, JSON.stringify({ ...plan, transactionHash: tx.hash, status: 'pending' }), { mode: 0o600 });
        const receipt = await tx.wait(Number(process.env.CHAIN_CONFIRMATIONS || 12));
        writeFileSync(out, JSON.stringify({ ...plan, transactionHash: tx.hash, blockHash: receipt.blockHash, blockNumber: receipt.blockNumber, status: receipt.status === 1 ? 'confirmed' : 'failed' }), { mode: 0o600 });
        console.log('Checkpoint confirmed');
      }
    }
  }
} finally { rpc.destroy(); }
