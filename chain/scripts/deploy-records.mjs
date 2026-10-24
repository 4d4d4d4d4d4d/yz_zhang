// Offline preparation is the default. Never put a private key in arguments or a public manifest.
import fs from 'node:fs';
import { JsonRpcProvider, Wallet, ContractFactory, keccak256 } from 'ethers';
import { compile } from './compile.mjs';
const env = name => { if (!process.env[name]) throw new Error(`Missing ${name}`); return process.env[name]; };
const rpcUrl = env('CHAIN_RPC_URL');
const provider = new JsonRpcProvider(rpcUrl);
try {
  const chainId = Number(env('CHAIN_ID'));
  if (!Number.isSafeInteger(chainId) || chainId <= 0 || (await provider.getNetwork()).chainId !== BigInt(chainId)) throw new Error('Wrong chain');
  const confirmations = Number(process.env.CHAIN_CONFIRMATIONS || 12);
  if (!Number.isInteger(confirmations) || confirmations < 1 || confirmations > 100) throw new Error('Invalid confirmation policy');
  const artifact = compile('BusinessRecords');
  const factory = new ContractFactory(artifact.abi, artifact.bytecode);
  const request = await factory.getDeployTransaction();
  const plan = { chainId, contractType: 'BusinessRecords', compiler: artifact.compiler, initCodeHash: keccak256(request.data), confirmations };
  if (process.env.CHAIN_SEND !== '1') {
    console.log(JSON.stringify({ dryRun: true, ...plan }, null, 2));
  } else {
    const receiptFile = env('CHAIN_RECEIPT_FILE');
    const manifestFile = env('RECORDS_MANIFEST_FILE');
    const publicRpc = new URL(env('RECORDS_PUBLIC_RPC_URL'));
    if (publicRpc.username || publicRpc.password || (publicRpc.protocol !== 'https:' && !(publicRpc.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(publicRpc.hostname)))) throw new Error('Invalid public RPC URL');
    const wallet = new Wallet(fs.readFileSync(env('CHAIN_KEY_FILE'), 'utf8').trim(), provider);
    let raw, hash;
    if (process.argv.includes('--resume')) {
      const pending = JSON.parse(fs.readFileSync(receiptFile, 'utf8'));
      if (pending.initCodeHash !== plan.initCodeHash || pending.chainId !== chainId || pending.deployer !== wallet.address) throw new Error('Resume plan mismatch');
      raw = pending.rawTransaction; hash = keccak256(raw);
      if (hash !== pending.transactionHash) throw new Error('Saved transaction corrupted');
    } else {
      const populated = await wallet.populateTransaction(request);
      raw = await wallet.signTransaction(populated); hash = keccak256(raw);
      // Exclusive creation BEFORE broadcast. If confirmation fails, --resume reuses precisely this transaction.
      fs.writeFileSync(receiptFile, JSON.stringify({ ...plan, deployer: wallet.address, transactionHash: hash, rawTransaction: raw, status: 'prepared' }, null, 2), { flag: 'wx', mode: 0o600 });
    }
    let receipt = await provider.getTransactionReceipt(hash);
    if (!receipt) {
      const known = await provider.getTransaction(hash);
      if (!known) await provider.broadcastTransaction(raw);
      receipt = await provider.waitForTransaction(hash, confirmations, 180000);
    } else if (await receipt.confirmations() < confirmations) receipt = await provider.waitForTransaction(hash, confirmations, 180000);
    if (!receipt || receipt.status !== 1 || !receipt.contractAddress) throw new Error('Not confirmed; retain receipt and use --resume, never blindly redeploy');
    const address = receipt.contractAddress;
    const manifest = { chainId, name: env('RECORDS_NETWORK_NAME'), rpcUrl: publicRpc.href, address,
      runtimeCodeHash: keccak256(await provider.getCode(address)),
      confirmations, testOnly: process.env.RECORDS_TEST_ONLY !== '0', deploymentBlock: receipt.blockNumber, transactionHash: hash };
    if (fs.existsSync(manifestFile)) {
      const existing = JSON.parse(fs.readFileSync(manifestFile, 'utf8'));
      if (JSON.stringify(existing) !== JSON.stringify(manifest)) throw new Error('Refusing to replace a different deployment manifest');
    } else fs.writeFileSync(manifestFile, JSON.stringify(manifest, null, 2) + '\n', { flag: 'wx' });
    // Retain the original signed transaction for idempotent incident recovery.
    fs.writeFileSync(receiptFile, JSON.stringify({ ...plan, deployer: wallet.address, rawTransaction: raw, transactionHash: hash,
      address, blockHash: receipt.blockHash, blockNumber: receipt.blockNumber, status: 'confirmed' }, null, 2), { mode: 0o600 });
    console.log(JSON.stringify({ address, transactionHash: hash, manifestFile }, null, 2));
  }
} finally { provider.destroy(); }
