import { useEffect, useState } from 'react';
import { Contract, formatUnits, parseUnits, id as hashText, ZeroAddress, isHexString, type ContractTransactionResponse } from 'ethers';
import { Link, useSearchParams } from 'react-router-dom';
import { canUseLocalDemo, parseDeployment, readContract, readDetail, verifyDeployment, walletContract, tokenAbi, type Deployment, type Detail } from '../chain/client';
import './Chain.css';

const states = ['不存在', '待接单确认', '待托管入金', '履约中', '已关闭'];
const stages = ['待交付', '待验收', '争议处理中', '已结算'];
const date = (v: bigint) => v ? new Date(Number(v) * 1000).toLocaleString() : '—';
const errorText = (e: unknown) => e instanceof Error ? ('shortMessage' in e ? String(e.shortMessage) : e.message) : String(e);

export default function Chain() {
  const [params] = useSearchParams();
  const [deployment, setDeployment] = useState<Deployment>();
  const [detail, setDetail] = useState<Detail>();
  const [account, setAccount] = useState('');
  const [demoAccount, setDemoAccount] = useState<number>();
  const [jobId, setJobId] = useState(params.get('id') || '1');
  const [loadedId, setLoadedId] = useState('');
  const [credit, setCredit] = useState(0n);
  const [balance, setBalance] = useState(0n);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [txHash, setTxHash] = useState('');
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [digest, setDigest] = useState('');
  const [split, setSplit] = useState('0');
  const [delegate, setDelegate] = useState('');
  const [executor, setExecutor] = useState('');
  const [arb, setArb] = useState('');
  const [reference, setReference] = useState(params.get('reference') || '');
  const [agreement, setAgreement] = useState(params.get('agreement') || '');
  const [fundingDate, setFundingDate] = useState('');
  const [reviewHours, setReviewHours] = useState('72');
  const [arbDays, setArbDays] = useState('14');
  const [fallback, setFallback] = useState('50');
  const [rows, setRows] = useState([{ amount: '', due: '' }]);
  const [createOpen, setCreateOpen] = useState(false);
  const d = deployment;
  const job = detail?.job;
  const current = job && detail?.milestones[Number(job.current)];
  const isRequester = !!account && account.toLowerCase() === job?.requester.toLowerCase();
  const isExecutor = !!account && account.toLowerCase() === job?.terms.executor.toLowerCase();
  const isArb = !!account && account.toLowerCase() === job?.terms.arbitrator.toLowerCase();
  const isDelegate = !!account && account.toLowerCase() === detail?.delegate.account.toLowerCase();
  const amount = (v: bigint) => d ? `${formatUnits(v, d.tokenDecimals)} ${d.tokenSymbol}` : '—';
  useEffect(() => {
    let active = true;
    fetch('/escrow-deployment.json', { cache: 'no-store' }).then(async r => {
      if (!r.ok || !r.headers.get('content-type')?.includes('json')) throw new Error('链上环境尚未配置，暂不能发起交易。');
      const config = parseDeployment(await r.json());
      const { provider } = readContract(config);
      try { await verifyDeployment(provider, config); }
      finally { provider.destroy(); }
      if (active) { setDeployment(config); setReady(true); }
    }).catch(e => { if (active) setError(errorText(e)); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (!deployment) return;
    let active = true;
    const { provider, contract } = readContract(deployment);
    const initialId = params.get('id') || '1';
    readDetail(contract, initialId).then(value => {
      if (active) { setDetail(value); setLoadedId(initialId); setJobId(initialId); }
    }).catch(e => { if (active) setError(errorText(e)); }).finally(() => provider.destroy());
    return () => { active = false; };
  }, [deployment, params]);
  async function load(id = jobId, wallet = account) {
    if (!d) return;
    const { provider, contract } = readContract(d);
    try {
      await verifyDeployment(provider, d);
      const result = await readDetail(contract, id); setDetail(result); setLoadedId(id); setJobId(id);
      if (wallet) {
        setCredit(await contract.credits(wallet));
        setBalance(await new Contract(d.token, tokenAbi, provider).balanceOf(wallet));
      }
    } finally { provider.destroy(); }
  }
  async function act(fn: () => Promise<void>) {
    setBusy(true); setError(''); setMessage(''); setTxHash('');
    try { await fn(); } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  }
  async function send(method: string, args: unknown[], requireParty?: string) {
    if (!d) throw new Error('链上环境尚未就绪');
    const { signer, contract } = await walletContract(d, demoAccount);
    const activeAccount = await signer.getAddress(); setAccount(activeAccount);
    if (requireParty && activeAccount.toLowerCase() !== requireParty.toLowerCase()) throw new Error('钱包账户已切换，请刷新并确认参与方身份');
    const tx = await contract.getFunction(method)(...args) as ContractTransactionResponse;
    setTxHash(tx.hash); setMessage(`交易已发送，等待 ${d.confirmations} 个区块确认…`);
    const receipt = await tx.wait(d.confirmations);
    if (!receipt || receipt.status !== 1) throw new Error('交易未成功确认');
    setMessage('交易已确认，链上状态已更新。');
    if (method === 'create') {
      for (const log of receipt.logs) {
        if (log.address.toLowerCase() !== d.address.toLowerCase()) continue;
        const parsed = contract.interface.parseLog(log);
        if (parsed?.name === 'Created') { await load(String(parsed.args.id), activeAccount); break; }
      }
      setCreateOpen(false);
    } else if (loadedId) await load(loadedId, activeAccount);
  }
  const hash = (value: string) => { if (!isHexString(value, 32)) throw new Error('请输入 0x 开头的 32 字节摘要'); return value; };
  const units = (value: string) => { if (!d) throw new Error('未配置代币'); return parseUnits(value, d.tokenDecimals); };
  const seconds = (value: string) => { const n = Math.floor(new Date(value).getTime() / 1000); if (!Number.isSafeInteger(n)) throw new Error('请填写有效时间'); return n; };
  const perform = (method: string, args: unknown[] = [loadedId], party?: string) => void act(() => send(method, args, party));
  return <div className="page chain-page">
    <header className="chain-hero">
      <div><span className="chain-eyebrow">TRUST THROUGH EXECUTION</span><h1>让约定，<br />成为可执行的承诺。</h1><p>资金按阶段托管，成果由双方验收。每一次交付、裁决与结算，都留下可核验的链上记录。</p></div>
      <div className="chain-flow" aria-label="智能合约流程"><span>01 约定</span><i>↓</i><span>02 托管</span><i>↓</i><span>03 交付</span><i>↓</i><span>04 结算</span></div>
    </header>
    <section className="card chain-network">
      <div><h2>{d?.name || '链上协作空间'}</h2><Link to="/records">股权、协议、合同与财务档案 →</Link><p className="muted">{d?.testOnly ? '测试网络 · 代币无真实价值' : '独立代币结算 · 不计入平台人民币余额'}{d ? ` · 服务费 ${d.feeBps / 100}%` : ''}</p>
      {d && <details><summary>核对部署信息</summary><p>网络编号 {d.chainId} · 确认数 {d.confirmations}</p><p>托管合约 <code>{d.address}</code></p><p>代币 <code>{d.token}</code></p><p>收款方 <code>{d.feeRecipient}</code></p><p>代码摘要 <code>{d.runtimeCodeHash}</code></p></details>}</div>
      <button disabled={busy || !ready} onClick={() => void act(async () => {
        if (!d) return; setDemoAccount(undefined); const { signer, contract } = await walletContract(d); const address = await signer.getAddress();
        setAccount(address); setCredit(await contract.credits(address)); setBalance(await new Contract(d.token, tokenAbi, signer).balanceOf(address));
      })}>{account ? `${account.slice(0, 6)}…${account.slice(-4)} · 切换后重连` : '连接钱包'}</button>
    </section>
    {d && canUseLocalDemo(d) && <section className="card"><h3>本机演示角色</h3><p className="muted">无需安装钱包，仅在本机测试链操作无价值的 DEMO 代币。测试链重启会重置记录。</p><div className="chain-toolbar">{[[1, '发布方'], [2, '执行方'], [3, '仲裁人']].map(([index, label]) => <button key={index} className="ghost" disabled={busy} onClick={() => void act(async () => { const selected = Number(index); const { signer, contract } = await walletContract(d, selected); const address = await signer.getAddress(); setDemoAccount(selected); setAccount(address); setCredit(await contract.credits(address)); setBalance(await new Contract(d.token, tokenAbi, signer).balanceOf(address)); })}>{demoAccount === index ? '当前：' : '切换为'}{label}</button>)}</div></section>}
    {error && <div className="card error" role="alert">{error}</div>}
    {(message || txHash) && <div className="card" role="status"><p>{message}</p>{txHash && <p>交易哈希 <code>{txHash}</code></p>}</div>}
    {account && <section className="chain-stats"><div><small>当前钱包余额</small><strong>{amount(balance)}</strong></div><div><small>已结算、待提取</small><strong>{amount(credit)}</strong></div><button disabled={busy || credit === 0n} onClick={() => perform('withdraw', [], account)}>提取至当前钱包</button></section>}
    <section className="card"><div className="chain-toolbar"><label>链上合约编号<input inputMode="numeric" value={jobId} onChange={e => setJobId(e.target.value)} /></label><button className="ghost" disabled={busy || !ready} onClick={() => void act(() => load())}>查看 / 刷新</button><button disabled={busy || !ready} onClick={() => setCreateOpen(!createOpen)}>发起链上协作</button></div></section>
    {createOpen && <form className="card chain-form" onSubmit={e => { e.preventDefault(); void act(async () => {
      if (!d) return;
      const terms = { executor, arbitrator: arb, agreementHash: hash(agreement), platformRef: hashText(reference),
        fundingDeadline: seconds(fundingDate), reviewPeriod: Number(reviewHours) * 3600,
        arbitrationPeriod: Number(arbDays) * 86400, timeoutExecutorBps: Number(fallback) * 100 };
      await send('create', [terms, rows.map(r => units(r.amount)), rows.map(r => seconds(r.due))]);
    }); }}>
      <h2>先把合作约定清楚</h2><p className="muted">条款提交后不可修改。请先交换并保存合同原文；链上摘要只能证明文件一致性，不能替代电子签约。截止时间是固定时间，争议不会自动顺延后续阶段。</p>
      <div className="chain-fields"><label>执行方钱包<input required value={executor} onChange={e => setExecutor(e.target.value)} placeholder="0x…" /></label><label>双方认可的仲裁人钱包<input required value={arb} onChange={e => setArb(e.target.value)} placeholder="0x…" /></label><label>合作编号（用于关联，不含个人信息）<input required value={reference} onChange={e => setReference(e.target.value)} /></label><label>合同原文摘要（32 字节）<input required value={agreement} onChange={e => setAgreement(e.target.value)} placeholder="0x…" /></label><label>入金截止时间<input required type="datetime-local" value={fundingDate} onChange={e => setFundingDate(e.target.value)} /></label><label>验收期（小时）<input required type="number" min="1" max="720" step="1" value={reviewHours} onChange={e => setReviewHours(e.target.value)} /></label><label>仲裁期（天）<input required type="number" min="1" max="90" step="1" value={arbDays} onChange={e => setArbDays(e.target.value)} /></label><label>仲裁超时分配给执行方（%，扣费前）<input required type="number" min="0" max="100" step="1" value={fallback} onChange={e => setFallback(e.target.value)} /></label></div>
      <h3>分期交付计划</h3>{rows.map((row, i) => <div className="chain-fields" key={i}><label>第 {i + 1} 期金额（{d?.tokenSymbol}）<input required inputMode="decimal" value={row.amount} onChange={e => setRows(rows.map((r, n) => n === i ? { ...r, amount: e.target.value } : r))} /></label><label>交付截止时间<input required type="datetime-local" value={row.due} onChange={e => setRows(rows.map((r, n) => n === i ? { ...r, due: e.target.value } : r))} /></label></div>)}
      <div className="chain-toolbar"><button type="button" className="ghost" disabled={rows.length >= 32} onClick={() => setRows([...rows, { amount: '', due: '' }])}>＋ 增加阶段</button>{rows.length > 1 && <button type="button" className="ghost" onClick={() => setRows(rows.slice(0, -1))}>移除末期</button>}<button disabled={busy || !account} type="submit">在钱包中确认发布</button></div>
    </form>}
    {job && detail && <>
      <section className="card"><div className="chain-toolbar"><h2>协作 #{loadedId}</h2><span className="badge">{states[Number(job.state)]}</span></div><div className="chain-stats"><div><small>约定总额</small><strong>{amount(job.total)}</strong></div><div><small>尚在托管</small><strong>{amount(job.remaining)}</strong></div><div><small>执行方所得服务费</small><strong>{d ? d.feeBps / 100 : 0}%</strong></div></div>
        <dl className="chain-terms"><dt>发布方</dt><dd>{job.requester}</dd><dt>执行方</dt><dd>{job.terms.executor}</dd><dt>仲裁人</dt><dd>{job.terms.arbitrator}</dd><dt>合同原文摘要</dt><dd>{job.terms.agreementHash}</dd><dt>完整链上条款摘要</dt><dd>{job.termsHash}</dd><dt>合作编号摘要</dt><dd>{job.terms.platformRef}</dd><dt>入金截止</dt><dd>{date(job.terms.fundingDeadline)}</dd><dt>验收 / 仲裁期限</dt><dd>{Number(job.terms.reviewPeriod) / 3600} 小时 / {Number(job.terms.arbitrationPeriod) / 86400} 天</dd><dt>仲裁超时预定分配</dt><dd>执行方 {Number(job.terms.timeoutExecutorBps) / 100}%（扣费前），其余退还发布方</dd></dl>
        <ol className="chain-milestones">{detail.milestones.map((m, i) => <li key={i} className={i === Number(job.current) && job.state === 3n ? 'active' : ''}><div><strong>{i + 1}. {amount(m.amount)}</strong><span className="badge">{job.state === 4n && m.stage !== 3n ? '已关闭（以结算事件为准）' : stages[Number(m.stage)]}</span></div><p>交付截止 {date(m.due)}</p>{m.stage >= 1n && <><p>交付摘要 <code>{m.delivery}</code></p><p>验收截止 {date(m.reviewDeadline)}</p></>}{m.stage >= 2n && m.arbitrationDeadline > 0n && <><p>争议摘要 <code>{m.dispute}</code></p><p>仲裁截止 {date(m.arbitrationDeadline)}</p></>}</li>)}</ol>
        <div className="chain-toolbar">
          {job.state === 1n && isExecutor && <button disabled={busy} onClick={() => perform('accept', [loadedId, job.termsHash], job.terms.executor)}>确认全部条款并接单</button>}
          {job.state === 2n && isRequester && <button disabled={busy} onClick={() => void act(async () => {
            if (!d) return;
            const { signer } = await walletContract(d, demoAccount); const active = await signer.getAddress();
            if (active.toLowerCase() !== job.requester.toLowerCase()) throw new Error('请使用发布方钱包');
            const token = new Contract(d.token, tokenAbi, signer);
            const allowance = await token.allowance(active, d.address) as bigint;
            // Reset nonzero approvals before replacing; never request unlimited allowance.
            if (allowance < job.total) {
              if (allowance > 0n) { const reset = await token.approve(d.address, 0); setTxHash(reset.hash); await reset.wait(d.confirmations); }
              const approval = await token.approve(d.address, job.total); setTxHash(approval.hash); setMessage('确认代币额度后，还需确认托管入金交易。'); await approval.wait(d.confirmations);
            }
            await send('fund', [loadedId], job.requester);
          })}>授权精确金额并托管 {amount(job.total)}</button>}
          {(job.state === 1n || job.state === 2n) && <button className="ghost" disabled={busy || !account} onClick={() => perform('closeUnfunded')}>{isRequester ? '关闭未入金合约' : '清理已过期合约'}</button>}
          {current?.stage === 1n && job.state === 3n && isRequester && <button disabled={busy} onClick={() => perform('approve', [loadedId], job.requester)}>验收通过，结算本期</button>}
          {current?.stage === 1n && job.state === 3n && <button className="ghost" disabled={busy || !account} onClick={() => perform('releaseAfterReview')}>验收超时，执行放款</button>}
          {current?.stage === 2n && job.state === 3n && <button className="ghost" disabled={busy || !account} onClick={() => perform('resolveAfterTimeout')}>仲裁超时，按约定分配</button>}
          {current?.stage === 0n && job.state === 3n && <button className="ghost" disabled={busy || !account} onClick={() => perform('refundOverdue')}>交付逾期，退回剩余资金</button>}
        </div>
      </section>
      {job.state === 3n && account && <section className="card chain-form"><h2>履约与协商</h2><p className="muted">操作权限和时间条件由链上合约校验。证据请在双方认可的渠道保存并共享；这里只提交文件摘要。</p><label>交付 / 争议 / 裁决文件摘要<input value={digest} onChange={e => setDigest(e.target.value)} placeholder="0x…" /></label><div className="chain-toolbar">
        {current?.stage === 0n && (isExecutor || isDelegate) && <button disabled={busy} onClick={() => void act(() => send('deliver', [loadedId, hash(digest)]))}>提交本期交付</button>}
        {current?.stage === 1n && (isRequester || isExecutor) && <button className="ghost" disabled={busy} onClick={() => void act(() => send('dispute', [loadedId, hash(digest)]))}>发起争议，冻结本期</button>}
      </div>
      {(isRequester || isExecutor || isArb) && <><label>分配给执行方的金额（扣费前，{d?.tokenSymbol}）<input inputMode="decimal" value={split} onChange={e => setSplit(e.target.value)} /></label><div className="chain-toolbar">
        {isArb && current?.stage === 2n && <button disabled={busy} onClick={() => void act(() => send('resolve', [loadedId, units(split), hash(digest)], job.terms.arbitrator))}>按此金额裁决本期</button>}
        {(isRequester || isExecutor) && <button className="ghost" disabled={busy} onClick={() => void act(() => send('proposeCancellation', [loadedId, units(split), Math.floor(Date.now() / 1000) + 86400]))}>提议终止全部剩余阶段（24 小时内有效）</button>}
      </div></>}
      {detail.cancellation.proposer !== ZeroAddress && <div className="chain-proposal"><p>终止提议：执行方 {amount(detail.cancellation.executorAmount)}（扣费前）<br />有效至 {date(detail.cancellation.expires)} · 提议版本 {String(detail.cancellation.revision)}</p><p>提出者 <code>{detail.cancellation.proposer}</code></p><button disabled={busy || !(isRequester || isExecutor) || detail.cancellation.revision !== job.revision || account.toLowerCase() === detail.cancellation.proposer.toLowerCase()} onClick={() => perform('acceptCancellation', [loadedId, detail.cancellation.revision, detail.cancellation.executorAmount])}>接受此分配并终止合作</button></div>}
      {isExecutor && <details><summary>机器代理授权（仅交付）</summary><p className="muted">代理不能入金、验收、仲裁、取消或提走你的资金。授权 7 天后自动失效，可随时撤销。</p><p>当前代理 <code>{detail.delegate.account}</code> · {date(detail.delegate.expires)}</p><label>代理钱包<input value={delegate} onChange={e => setDelegate(e.target.value)} /></label><div className="chain-toolbar"><button disabled={busy} onClick={() => perform('setDelegate', [loadedId, delegate, Math.floor(Date.now() / 1000) + 7 * 86400], job.terms.executor)}>授权交付</button><button className="ghost" disabled={busy} onClick={() => perform('setDelegate', [loadedId, ZeroAddress, 0], job.terms.executor)}>撤销代理</button></div></details>}
      </section>}
    </>}
    <footer className="chain-footnote">链上记录不自动建立实名身份、公司股权或法定签章。当前链上协作与平台原有任务结算独立；不要为同一合作重复支付。</footer>
  </div>;
}
