import { BrowserProvider, Contract, JsonRpcProvider, keccak256, getAddress, type Eip1193Provider } from 'ethers';
import abi from './escrow-abi.json';
export type Deployment = {
  chainId: number; name: string; rpcUrl: string; address: string; token: string;
  runtimeCodeHash: string; tokenSymbol: string; tokenDecimals: number;
  feeBps: number; feeRecipient: string; confirmations: number; testOnly: boolean;
};
export type Job = {
  requester: string; terms: { executor: string; arbitrator: string; agreementHash: string; platformRef: string;
    fundingDeadline: bigint; reviewPeriod: bigint; arbitrationPeriod: bigint; timeoutExecutorBps: bigint };
  termsHash: string; state: bigint; current: bigint; count: bigint; total: bigint; remaining: bigint; revision: bigint;
};
export type Milestone = { amount: bigint; due: bigint; reviewDeadline: bigint; arbitrationDeadline: bigint;
  stage: bigint; delivery: string; dispute: string };
export type Cancellation = { proposer: string; executorAmount: bigint; revision: bigint; expires: bigint };
export type Detail = { job: Job; milestones: Milestone[]; cancellation: Cancellation; delegate: { account: string; expires: bigint } };
export const tokenAbi = ['function approve(address,uint256) returns(bool)', 'function allowance(address,address) view returns(uint256)',
  'function balanceOf(address) view returns(uint256)', 'function decimals() view returns(uint8)', 'function symbol() view returns(string)'];
export function parseDeployment(value: unknown): Deployment {
  const d = value as Deployment;
  if (!d || !Number.isSafeInteger(d.chainId) || d.chainId <= 0 || !d.name || typeof d.testOnly !== 'boolean'
      || !Number.isInteger(d.tokenDecimals) || d.tokenDecimals < 0 || d.tokenDecimals > 36
      || !Number.isInteger(d.feeBps) || d.feeBps < 0 || d.feeBps > 1000
      || !Number.isInteger(d.confirmations) || d.confirmations < 1 || d.confirmations > 100
      || !/^0x[0-9a-fA-F]{64}$/.test(d.runtimeCodeHash)) throw new Error('链上部署配置无效');
  getAddress(d.address); getAddress(d.token); getAddress(d.feeRecipient);
  const url = new URL(d.rpcUrl, window.location.origin);
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['127.0.0.1', 'localhost'].includes(url.hostname))) throw new Error('RPC 必须使用 HTTPS 或本机地址');
  if (url.username || url.password) throw new Error('RPC 配置不能包含账户密码');
  return { ...d, rpcUrl: url.href };
}
export async function verifyDeployment(provider: JsonRpcProvider | BrowserProvider, d: Deployment) {
  if ((await provider.getNetwork()).chainId !== BigInt(d.chainId)) throw new Error(`请切换钱包至 ${d.name}（${d.chainId}）`);
  const code = await provider.getCode(d.address);
  if (code === '0x' || keccak256(code) !== d.runtimeCodeHash) throw new Error('链上合约代码与部署记录不一致，已禁止交易');
  const c = new Contract(d.address, abi, provider);
  const [token, feeBps, recipient] = await Promise.all([c.token(), c.feeBps(), c.feeRecipient()]);
  if (getAddress(token) !== getAddress(d.token) || Number(feeBps) !== d.feeBps || getAddress(recipient) !== getAddress(d.feeRecipient)) throw new Error('链上结算参数与部署记录不一致');
  const erc20 = new Contract(d.token, tokenAbi, provider);
  if (Number(await erc20.decimals()) !== d.tokenDecimals || await erc20.symbol() !== d.tokenSymbol) throw new Error('代币信息不匹配');
}
export function readContract(d: Deployment) {
  const provider = new JsonRpcProvider(d.rpcUrl);
  return { provider, contract: new Contract(d.address, abi, provider) };
}
export async function readDetail(c: Contract, id: string): Promise<Detail> {
  if (!/^[1-9]\d*$/.test(id)) throw new Error('请输入正整数合约编号');
  const job = await c.getJob(id) as Job;
  if (job.state === 0n) throw new Error('未找到链上合约');
  const milestones = await Promise.all(Array.from({ length: Number(job.count) }, (_, i) => c.milestones(id, i))) as Milestone[];
  return { job, milestones, cancellation: await c.cancellations(id), delegate: await c.delegates(id) };
}
export function injectedWallet(): Eip1193Provider {
  const ethereum = (window as Window & { ethereum?: Eip1193Provider }).ethereum;
  if (!ethereum) throw new Error('请在支持以太坊钱包的浏览器中打开此页；手机可使用钱包内置浏览器。');
  return ethereum;
}
export function canUseLocalDemo(d: { testOnly: boolean; chainId: number; rpcUrl: string }) {
  const url = new URL(d.rpcUrl, window.location.origin);
  return d.testOnly && d.chainId === 31337 && ['localhost', '127.0.0.1'].includes(window.location.hostname)
    && url.protocol === 'http:' && url.hostname === '127.0.0.1' && url.port === '18547';
}
export async function walletContract(d: Deployment, demoAccount?: number) {
  if (demoAccount !== undefined && (!canUseLocalDemo(d) || ![1, 2, 3].includes(demoAccount))) throw new Error('仅允许本机测试角色');
  const provider = demoAccount === undefined ? new BrowserProvider(injectedWallet()) : new JsonRpcProvider(d.rpcUrl);
  await verifyDeployment(provider, d);
  const signer = await provider.getSigner(demoAccount);
  return { provider, signer, contract: new Contract(d.address, abi, signer) };
}
