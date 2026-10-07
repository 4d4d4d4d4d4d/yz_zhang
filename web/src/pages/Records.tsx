import { useEffect, useState } from 'react';
import { BrowserProvider, Contract, JsonRpcProvider, ZeroAddress, id, isHexString, keccak256, getAddress } from 'ethers';
import { Link } from 'react-router-dom';
import abi from '../chain/records-abi.json';
import { canUseLocalDemo, injectedWallet } from '../chain/client';
import { encryptDocument, decryptDocument, downloadFile, type Archive, type Recovery } from '../chain/documents';
import './Chain.css';
type Config = { chainId: number; name: string; rpcUrl: string; address: string; runtimeCodeHash: string; confirmations: number; testOnly: boolean };
type Entry = { commitment: string; previous: string; recordHash: string; author: string; recordedAt: bigint; policyVersion: bigint; approvals: bigint; quorum: bigint; kind: bigint; correction: boolean };
type View = { controller: string; pendingController: string; policy: string[]; quorum: number; latest: bigint; entries: { version: bigint; record: Entry; signers: string[]; approvals: boolean[] }[] };
const kinds = ['公司股权', '合作协议', '法律合同', '财务记录'];
const sampleKeys = ['DEMO-EQUITY', 'DEMO-AGREEMENT', 'DEMO-LEGAL', 'DEMO-FINANCIAL'];
const errorText = (e: unknown) => e instanceof Error ? ('shortMessage' in e ? String(e.shortMessage) : e.message) : String(e);
export default function Records() {
  const [config, setConfig] = useState<Config>();
  const [org, setOrg] = useState('1'), [key, setKey] = useState(sampleKeys[0]), [kind, setKind] = useState(0);
  const [loaded, setLoaded] = useState<{ org: string; key: string }>();
  const [view, setView] = useState<View>();
  const [demoAccount, setDemoAccount] = useState<number>();
  const [account, setAccount] = useState(''), [error, setError] = useState(''), [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false), [commitment, setCommitment] = useState(''), [correction, setCorrection] = useState(false);
  const [encrypted, setEncrypted] = useState<{ archive: Archive; recovery: Recovery }>(), [saved, setSaved] = useState(false);
  const [archive, setArchive] = useState<Archive>(), [recovery, setRecovery] = useState<Recovery>();
  const [identity, setIdentity] = useState(''), [signers, setSigners] = useState(''), [quorum, setQuorum] = useState('1');
  const [publisher, setPublisher] = useState(''), [mask, setMask] = useState('8'), [nextController, setNextController] = useState('');
  const isController = account && view?.controller.toLowerCase() === account.toLowerCase();
  async function verify(p: JsonRpcProvider | BrowserProvider, c: Config) {
    if ((await p.getNetwork()).chainId !== BigInt(c.chainId)) throw new Error(`请切换至 ${c.name}（${c.chainId}）`);
    const code = await p.getCode(c.address);
    if (code === '0x' || keccak256(code) !== c.runtimeCodeHash) throw new Error('企业档案合约代码核验失败');
  }
  useEffect(() => {
    let active = true;
    fetch('/business-records-deployment.json', { cache: 'no-store' }).then(async response => {
      if (!response.ok || !response.headers.get('content-type')?.includes('json')) throw new Error('企业档案链上环境尚未配置');
      const c = await response.json() as Config;
      if (!Number.isSafeInteger(c.chainId) || c.chainId <= 0 || !Number.isInteger(c.confirmations) || c.confirmations < 1 || c.confirmations > 100 || !isHexString(c.runtimeCodeHash, 32) || typeof c.testOnly !== 'boolean') throw new Error('部署配置无效');
      getAddress(c.address); const url = new URL(c.rpcUrl);
      if (url.username || url.password || (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname)))) throw new Error('RPC 地址不安全');
      const p = new JsonRpcProvider(c.rpcUrl); try { await verify(p, c); } finally { p.destroy(); }
      if (active) setConfig(c);
    }).catch(e => { if (active) setError(errorText(e)); });
    return () => { active = false; };
  }, []);
  async function act(fn: () => Promise<void>) { setBusy(true); setError(''); setStatus(''); try { await fn(); } catch (e) { setError(errorText(e)); } finally { setBusy(false); } }
  async function load(targetOrg = org, targetKey = key) {
    if (!config) throw new Error('环境未就绪');
    if (!/^[1-9]\d*$/.test(targetOrg) || !targetKey.trim()) throw new Error('请输入组织编号和档案编号');
    const p = new JsonRpcProvider(config.rpcUrl);
    try {
      await verify(p, config); const c = new Contract(config.address, abi, p);
      const organization = await c.organizations(targetOrg);
      if (organization.controller === ZeroAddress) throw new Error('组织档案空间不存在');
      const latest = await c.latestVersion(targetOrg, id(targetKey)) as bigint;
      const entries: View['entries'] = [];
      // Display the most recent 50 versions; all earlier versions remain queryable by ABI.
      for (let v = latest; v > 0n && v > latest - 50n; v--) {
        const record = await c.records(targetOrg, id(targetKey), v) as Entry;
        const people = await c.getSigners(record.recordHash) as string[];
        entries.push({ version: v, record, signers: people, approvals: await Promise.all(people.map(a => c.approvedBy(record.recordHash, a))) });
      }
      setView({ controller: organization.controller, pendingController: organization.pendingController, policy: await c.getPolicy(targetOrg), quorum: Number(organization.quorum), latest, entries });
      setLoaded({ org: targetOrg, key: targetKey });
      if (entries[0]) setKind(Number(entries[0].record.kind));
    } finally { p.destroy(); }
  }
  async function write(method: string, args: unknown[]) {
    if (!config) throw new Error('环境未就绪');
    if (demoAccount !== undefined && (!canUseLocalDemo(config) || ![0, 1, 2].includes(demoAccount))) throw new Error('仅允许本机测试角色');
    const p = demoAccount === undefined ? new BrowserProvider(injectedWallet()) : new JsonRpcProvider(config.rpcUrl); await verify(p, config); const signer = await p.getSigner(demoAccount);
    setAccount(await signer.getAddress()); const c = new Contract(config.address, abi, signer);
    const tx = await c.getFunction(method)(...args); setStatus(`已发送 ${tx.hash}，等待 ${config.confirmations} 个区块确认…`);
    const receipt = await tx.wait(config.confirmations); if (!receipt || receipt.status !== 1) throw new Error('交易未确认成功');
    setStatus(`交易已确认：${tx.hash}`);
    if (method === 'createOrganization') {
      for (const log of receipt.logs) { if (log.address.toLowerCase() !== config.address.toLowerCase()) continue; const parsed = c.interface.parseLog(log);
        if (parsed?.name === 'OrganizationCreated') { setOrg(String(parsed.args.organization)); await load(String(parsed.args.organization)); break; } }
    } else if (loaded) await load(loaded.org, loaded.key);
  }
  const signerList = () => signers.split(/[\s,，]+/).filter(Boolean).map(getAddress);
  const perform = (method: string, args: unknown[]) => void act(() => write(method, args));
  return <div className="page chain-page">
    <header className="chain-hero"><div><span className="chain-eyebrow">AN ORGANIZATION WITH A MEMORY</span><h1>每一个重要约定，<br />都有来处，有据可查。</h1><p>从股权变化到合作协议，从法律合同到财务凭证。保留每个版本，让确认责任与变更历史清晰可见。</p></div><div className="chain-flow">{kinds.map(k => <span style={{ padding: '10px 0' }} key={k}>{k}</span>)}</div></header>
    <section className="card chain-network"><div><h2>企业可信档案</h2><p className="muted">{config?.name || '等待部署配置'} · {config?.testOnly ? '测试数据，不代表真实公司' : '加密原文保存在链下，链上仅记录摘要'}</p><Link to="/chain">任务托管与结算 →</Link>{config && <p><code>{config.address}</code></p>}</div><button disabled={busy || !config} onClick={() => void act(async () => { if (!config) return; setDemoAccount(undefined); const p = new BrowserProvider(injectedWallet()); await verify(p, config); setAccount(await (await p.getSigner()).getAddress()); })}>{account ? `${account.slice(0, 6)}…${account.slice(-4)} · 重新连接` : '连接钱包'}</button></section>
    {config && canUseLocalDemo(config) && <section className="card"><h3>本机演示角色</h3><p className="muted">这些账户仅用于合成测试档案，不代表真实公司或法律签署。</p><div className="chain-toolbar">{[[0, '组织控制人'], [1, '确认人 A'], [2, '确认人 B']].map(([n, label]) => <button key={n} className="ghost" disabled={busy} onClick={() => void act(async () => { const p = new JsonRpcProvider(config.rpcUrl); try { await verify(p, config); setAccount(await (await p.getSigner(Number(n))).getAddress()); setDemoAccount(Number(n)); } finally { p.destroy(); } })}>{demoAccount === n ? '当前：' : '切换为'}{label}</button>)}</div></section>}
    {error && <p className="card error" role="alert">{error}</p>}{status && <p className="card" role="status" style={{ overflowWrap: 'anywhere' }}>{status}</p>}
    <section className="card chain-form"><h2>查阅与版本追溯</h2><div className="chain-fields"><label>组织链上编号<input value={org} onChange={e => setOrg(e.target.value)} inputMode="numeric" /></label><label>档案编号（请勿包含姓名或证件号码）<input value={key} onChange={e => setKey(e.target.value)} /></label></div><div className="chain-toolbar">{kinds.map((k, i) => <button key={k} className="ghost" disabled={busy} onClick={() => { setKind(i); setKey(sampleKeys[i]); }}>{k}</button>)}<button disabled={busy || !config} onClick={() => void act(() => load())}>查询 / 刷新</button></div></section>
    {view && loaded && <section className="card"><h2>组织 #{loaded.org} · {loaded.key}</h2><p>控制账户 <code>{view.controller}</code></p><p className="muted">当前提交规则：{view.quorum} / {view.policy.length} 人确认。以下每一版使用提交时的规则，规则变更不影响旧版本。</p>{view.entries.length === 0 && <p>此编号尚无记录，可发布首个版本。</p>}<ol className="chain-milestones">{view.entries.map(({ version, record, signers: people, approvals }) => <li key={String(version)}><div><strong>v{String(version)} · {kinds[Number(record.kind)]}{record.correction ? ' · 更正声明' : ''}</strong><span className="badge">{record.approvals >= record.quorum ? '达到约定确认数' : '待确认'} {String(record.approvals)}/{String(record.quorum)}</span></div><p>{new Date(Number(record.recordedAt) * 1000).toLocaleString()} · 提交者 <code>{record.author}</code></p><p>原文承诺摘要 <code>{record.commitment}</code></p><p>本版记录哈希 <code>{record.recordHash}</code></p><p>前版记录哈希 <code>{record.previous}</code></p><details><summary>确认人及规则版本 {String(record.policyVersion)}</summary>{people.map((a, i) => <p key={a}><code>{a}</code> · {approvals[i] ? '已确认' : '未确认 / 已撤回'}</p>)}</details>{people.some(a => a.toLowerCase() === account.toLowerCase()) && <div className="chain-toolbar"><button disabled={busy} onClick={() => perform('attest', [loaded.org, id(loaded.key), version, record.recordHash, true])}>确认此版本</button><button className="ghost" disabled={busy} onClick={() => perform('attest', [loaded.org, id(loaded.key), version, record.recordHash, false])}>撤回我的确认（保留事件）</button></div>}</li>)}</ol>{view.latest > 50n && <p className="muted">显示最近 50 版；更早版本可通过合约 records 接口按版本查询。</p>}</section>}
    <section className="card chain-form"><h2>加密原文与核验</h2><p className="muted">文件只在当前设备加密，不上传服务器或区块链。请分别备份密文与恢复密钥，并通过安全渠道共享给确认人；丢失密钥将无法恢复原文。</p><label>选择待存证文件（最大 10 MB）<input type="file" disabled={busy} onChange={e => { const file = e.target.files?.[0]; if (file) void act(async () => { if (file.size === 0 || file.size > 10 * 1024 * 1024) throw new Error('文件须为 1 字节至 10 MB'); const result = await encryptDocument(new Uint8Array(await file.arrayBuffer()), file.name, file.type); setEncrypted(result); setCommitment(result.archive.commitment); setSaved(false); }); }} /></label>{encrypted && <><p><code>{encrypted.archive.commitment}</code></p><div className="chain-toolbar"><button className="ghost" onClick={() => downloadFile(JSON.stringify(encrypted.archive), 'record.encrypted.json')}>下载加密档案</button><button className="ghost" onClick={() => downloadFile(JSON.stringify(encrypted.recovery), 'record.recovery.private.json')}>下载恢复密钥</button></div><label><input type="checkbox" checked={saved} onChange={e => setSaved(e.target.checked)} />我已分别保存加密档案和恢复密钥</label></>}
      <details><summary>核验并恢复已有档案</summary><label>加密档案 JSON<input type="file" accept=".json" onChange={e => { const file = e.target.files?.[0]; if (file) void act(async () => { if (file.size > 22 * 1024 * 1024) throw new Error('档案过大'); setArchive(JSON.parse(await file.text())); }); }} /></label><label>恢复密钥 JSON<input type="file" accept=".json" onChange={e => { const file = e.target.files?.[0]; if (file) void act(async () => { if (file.size > 65536) throw new Error('恢复文件过大'); setRecovery(JSON.parse(await file.text())); }); }} /></label><label>需核对的链上原文承诺摘要<input value={commitment} onChange={e => setCommitment(e.target.value)} /></label><button disabled={busy || !archive || !recovery} onClick={() => void act(async () => { if (!archive || !recovery) return; const bytes = await decryptDocument(archive, recovery, commitment); downloadFile(bytes, recovery.name || 'verified-document', recovery.type || 'application/octet-stream'); setStatus('解密及摘要核验通过，已下载原文。'); })}>核验摘要并下载原文</button></details>
    </section>
    {loaded && view && <section className="card chain-form"><h2>追加记录到 {loaded.key}</h2><p className="muted">新版本从 v{String(view.latest)} 延续。旧版本不会被覆盖；提交不代表所有确认人已认可，也不自动完成工商变更。</p><label>记录类型<select value={kind} disabled={view.latest > 0n} onChange={e => setKind(Number(e.target.value))}>{kinds.map((k, i) => <option key={k} value={i}>{k}</option>)}</select></label><label>原文承诺摘要<input value={commitment} onChange={e => setCommitment(e.target.value)} placeholder="0x…" /></label><label><input type="checkbox" checked={correction} onChange={e => setCorrection(e.target.checked)} disabled={view.latest === 0n} />这是对前版的更正 / 撤销声明，理由和依据包含在新原文中</label><button disabled={busy || !account || (!!encrypted && !saved)} onClick={() => void act(async () => { if (!isHexString(commitment, 32)) throw new Error('摘要必须为 32 字节'); await write('append', [loaded.org, id(loaded.key), view.latest, kind, commitment, correction && view.latest > 0n]); })}>发布新版本，等待约定人员确认</button></section>}
    <section className="card chain-form"><details><summary>建立组织档案空间 / 设置确认规则</summary><p className="muted">空间编号只代表链上控制权，不能当作工商实名核验。企业建议用已建立的多签控制账户管理。控制账户可改变未来版本的规则，所有变更有链上事件。</p><label>组织身份材料承诺摘要<input value={identity} onChange={e => setIdentity(e.target.value)} placeholder="0x…" /></label><label>确认人钱包（逗号分隔，最多 32 人）<textarea value={signers} onChange={e => setSigners(e.target.value)} /></label><label>所需确认人数<input type="number" min="1" max="32" value={quorum} onChange={e => setQuorum(e.target.value)} /></label><div className="chain-toolbar"><button disabled={busy || !account} onClick={() => void act(async () => { if (!isHexString(identity, 32)) throw new Error('身份材料摘要必须为 32 字节'); await write('createOrganization', [identity, signerList(), Number(quorum)]); })}>建立新空间</button>{isController && loaded && <button className="ghost" disabled={busy} onClick={() => void act(() => write('setPolicy', [loaded.org, signerList(), Number(quorum)]))}>设置后续版本的确认规则</button>}</div></details>
      {isController && loaded && <details><summary>机器提交授权与控制账户交接</summary><label>机器 / 记录员钱包<input value={publisher} onChange={e => setPublisher(e.target.value)} /></label><label>允许提交的范围<select value={mask} onChange={e => setMask(e.target.value)}><option value="1">股权</option><option value="2">协议</option><option value="4">法律合同</option><option value="8">财务</option><option value="15">全部四类</option><option value="0">撤销全部提交权限</option></select></label><button disabled={busy} onClick={() => perform('setGrant', [loaded.org, publisher, Number(mask), Math.floor(Date.now() / 1000) + 7 * 86400])}>设置 7 天提交授权（不含确认权）</button><label>下一控制账户<input value={nextController} onChange={e => setNextController(e.target.value)} /></label><button className="ghost" disabled={busy} onClick={() => perform('proposeController', [loaded.org, nextController])}>提议控制权交接，需对方确认</button></details>}
      {loaded && view?.pendingController.toLowerCase() === account.toLowerCase() && account && <button disabled={busy} onClick={() => perform('acceptController', [loaded.org])}>接受组织控制权</button>}
    </section><footer className="chain-footnote">链上记录可核验版本与签署钱包，但不能单独证明原始事实或法定身份。财务、股权、合同的法定效力仍依赖真实材料、有效授权与适用程序。</footer>
  </div>;
}
