import {
  apiErrorText, fmtYuan,
  type CompliancePath, type ContributionKind, type ContributionView,
  type RiskDisclosure, type ShareRow, type VentureDetail, type VentureView,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from '../store';

const KIND_LABEL: Record<ContributionKind, string> = {
  time: '时间/人力', money: '资金', ip: '知识产权', resource: '资源/渠道', other: '其他',
};

/** UI-070~074 早期合作体（50 号 spec 的界面侧）。
 *
 * 这一页每一次点击都有真实后果，而且后果不对称：加入的人以为是「加个群」，
 * 实际是投入可能血本无归、份额会被后来者稀释、且不可转让不可赎回。
 *
 * 所以这里有一半代码在做同一件事——**把服务端已经写好的那些话原样说出来**。
 * 风险不是免责声明，是决策所需的信息（59 号 spec）。
 */
export default function Ventures() {
  const { client } = useApp();
  const [mine, setMine] = useState<Array<VentureView & { role: string }>>([]);
  const [current, setCurrent] = useState<number | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setMine(await client.myVentures().catch(() => []));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  return (
    <div className="page">
      <div className="card">
        <h3>早期合作体</h3>
        <p className="muted">
          贡献即份额：你投入的时间、资金、知识产权由其他成员确认计价，
          份额按已确认贡献计算。<strong>只分配合作体已经实际收到的钱</strong>，
          平台不承诺任何回报。
        </p>
        {error && <p className="error">{error}</p>}
        <div className="list">
          {mine.length === 0 && <p className="muted">你还没有加入任何合作体。</p>}
          {mine.map((v) => (
            <div className="task-item" key={v.id}>
              <div>
                <strong>{v.name}</strong> <span className="badge">{v.role}</span>
                <p className="muted">{v.category || '未分类'} · {v.purpose || '未填写目标'}</p>
              </div>
              <button className="ghost" onClick={() => setCurrent(v.id)}>打开</button>
            </div>
          ))}
        </div>
      </div>

      <CreateVenture onCreated={() => void load()} onError={setError} />
      {current !== null && <VentureDetailCard ventureId={current} onChanged={() => void load()} />}
    </div>
  );
}

/** UI-070 创建之前也要签风险揭示书——发起人承担的风险不比别人少。 */
function CreateVenture({ onCreated, onError }: { onCreated: () => void; onError: (s: string) => void }) {
  const { client } = useApp();
  const [doc, setDoc] = useState<RiskDisclosure | null>(null);
  const [open, setOpen] = useState(false);
  const [read, setRead] = useState(false);
  const [form, setForm] = useState({ name: '', purpose: '', category: '' });

  useEffect(() => { void client.ventureRiskDisclosure().then(setDoc).catch(() => {}); }, [client]);

  async function submit() {
    if (!doc) return;
    try {
      // UI-070 版本号用**服务端给的**：写死的话，风险揭示书改版后
      // 用户签的是旧版而界面显示新版，签署记录与他看到的内容对不上
      await client.createVenture(form.name, form.purpose, form.category, doc.version);
      setOpen(false); setRead(false); setForm({ name: '', purpose: '', category: '' });
      onCreated();
    } catch (err) {
      onError(apiErrorText(err));
    }
  }

  if (!open) {
    return (
      <div className="card">
        <button onClick={() => setOpen(true)}>发起一个合作体</button>
      </div>
    );
  }
  return (
    <div className="card">
      <h3>发起合作体</h3>
      <label>名称<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
      <label>目标<textarea rows={2} value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })} /></label>
      <label>类目<input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} /></label>
      {doc && <RiskDisclosureBlock doc={doc} read={read} onRead={setRead} />}
      <div className="row">
        <button disabled={!read || form.name.trim().length < 2} onClick={() => void submit()}>创建</button>
        <button className="ghost" onClick={() => setOpen(false)}>取消</button>
      </div>
    </div>
  );
}

/** UI-070 整篇展示，不是一行小字加个链接。
 *  把风险折叠起来，等于知道它会影响决定、却又不希望它影响决定。 */
function RiskDisclosureBlock({ doc, read, onRead }: {
  doc: RiskDisclosure; read: boolean; onRead: (v: boolean) => void;
}) {
  return (
    <div data-testid="risk-disclosure" style={{ marginTop: 12 }}>
      <h4>{doc.title}<span className="badge">{doc.version}</span></h4>
      <ol>
        {doc.points.map((p, i) => <li key={i}>{p}</li>)}
      </ol>
      <pre className="agent-output">{doc.text}</pre>
      <label className="row" style={{ display: 'flex' }}>
        <input type="checkbox" style={{ width: 'auto' }} checked={read}
               onChange={(e) => onRead(e.target.checked)} />
        我已阅读并理解上述风险
      </label>
    </div>
  );
}

function VentureDetailCard({ ventureId, onChanged }: { ventureId: number; onChanged: () => void }) {
  const { client } = useApp();
  const [detail, setDetail] = useState<VentureDetail | null>(null);
  const [contribs, setContribs] = useState<ContributionView[]>([]);
  const [shares, setShares] = useState<{ shares: ShareRow[]; total_bps: number; basis: string } | null>(null);
  const [path, setPath] = useState<CompliancePath | null>(null);
  const [error, setError] = useState('');
  const [form, setForm] = useState<{ kind: ContributionKind; description: string }>({
    kind: 'time', description: '',
  });
  const [amount, setAmount] = useState('');

  const load = useCallback(async () => {
    setDetail(await client.venture(ventureId).catch(() => null));
    setContribs(await client.ventureContributions(ventureId).catch(() => []));
    setShares(await client.ventureShares(ventureId).catch(() => null));
    setPath(await client.ventureCompliancePath(ventureId).catch(() => null));
  }, [client, ventureId]);
  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<unknown>) {
    setError('');
    try { await fn(); await load(); onChanged(); } catch (err) { setError(apiErrorText(err)); }
  }

  if (!detail) return null;

  return (
    <>
      <div className="card">
        <h3>{detail.name}</h3>
        <p className="muted">
          成员 {detail.members.length} 人 · 已实现资金{' '}
          <span className="price">{fmtYuan(detail.realized_funds_cents)}</span>
        </p>
        {error && <p className="error">{error}</p>}

        <h4>份额</h4>
        <table>
          <thead><tr><th>成员</th><th>已确认贡献</th><th>份额</th></tr></thead>
          <tbody>
            {(shares?.shares ?? detail.shares).map((s) => (
              <tr key={s.user_id}>
                <td>#{s.user_id}</td>
                <td className="muted">{fmtYuan(s.valued_cents)}</td>
                <td>{(s.share_bps / 100).toFixed(2)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
        {/* UI-071 口径说明来自服务端，与算法同源——这是一条有后果的解释 */}
        {shares && <p className="muted" data-testid="share-basis">{shares.basis}</p>}

        <h4>分配</h4>
        {/* UI-073 只分已实现收益：这是这个模式不变成「承诺收益的募集」的结构性条件 */}
        <p className="muted">
          只能分配合作体<strong>已经实际收到</strong>的钱，当前可分配{' '}
          {fmtYuan(detail.realized_funds_cents)}。
        </p>
        <div className="row">
          <input style={{ width: 140 }} type="number" min={0.01} step={0.01} placeholder="金额（元）"
                 value={amount} onChange={(e) => setAmount(e.target.value)} />
          <button disabled={!amount}
                  onClick={() => act(async () => {
                    await client.distributeVenture(ventureId, Math.round(parseFloat(amount) * 100));
                    setAmount('');
                  })}>
            按当前份额分配
          </button>
        </div>
      </div>

      <div className="card">
        <h3>贡献</h3>
        <div className="row">
          <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as ContributionKind })}>
            {Object.entries(KIND_LABEL).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </select>
          <input className="grow" placeholder="做了什么（计价由其他成员确认）"
                 value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          <button disabled={form.description.trim().length < 2}
                  onClick={() => act(async () => {
                    await client.submitContribution(ventureId, form.kind, form.description);
                    setForm({ ...form, description: '' });
                  })}>
            登记贡献
          </button>
        </div>
        <div className="list" style={{ marginTop: 12 }}>
          {contribs.length === 0 && <p className="muted">还没有贡献记录。</p>}
          {contribs.map((c) => (
            <div className="task-item" key={c.id}>
              <div>
                <strong>{KIND_LABEL[c.kind] ?? c.kind}</strong> · {c.description}
                <p className="muted">
                  #{c.user_id} · {c.status === 'confirmed' ? `已计价 ${fmtYuan(c.valued_cents)}` : '待确认'}
                  {c.confirm_note && ` · ${c.confirm_note}`}
                </p>
              </div>
              {/* UI-072 读服务端的 can_confirm：自己的贡献不能自己确认，
                  这个条件客户端不重算——判断只有一个来源 */}
              {c.can_confirm && (
                <button onClick={() => {
                  const yuan = prompt('这笔贡献值多少钱（元）？确认会直接改变所有人的份额比例：');
                  if (yuan) void act(() => client.confirmContribution(
                    ventureId, c.id, Math.round(parseFloat(yuan) * 100),
                  ));
                }}>确认并计价</button>
              )}
            </div>
          ))}
        </div>
      </div>

      {path && <CompliancePathCard path={path} />}
    </>
  );
}

/** UI-074 合规路径：告诉你需要什么，不拦住你。
 *  `why` 必须显示——只给清单不给理由，用户不知道哪些能省、哪些不能。 */
function CompliancePathCard({ path }: { path: CompliancePath }) {
  const section = (title: string, items: CompliancePath['documents']) => (
    items.length > 0 && (
      <>
        <h4>{title}</h4>
        <div className="list">
          {items.map((i) => (
            <div className="task-item" key={i.key}>
              <div>
                <strong>{i.title}</strong>{' '}
                <span className={`badge ${i.status === 'ready' ? 'ok' : i.status === 'todo' ? 'warn' : ''}`}>
                  {i.status === 'ready' ? '已就绪' : i.status === 'todo' ? '待办' : '不适用'}
                </span>
                <p className="muted">为什么需要：{i.why}</p>
                {i.action && <p className="muted">怎么做：{i.action}</p>}
              </div>
            </div>
          ))}
        </div>
      </>
    )
  );
  return (
    <div className="card">
      <h3>合规路径</h3>
      {section('必备文书', path.documents)}
      {section('登记与资质', path.registrations)}
      {path.notices.length > 0 && (
        <ul className="muted">{path.notices.map((n, i) => <li key={i}>{n}</li>)}</ul>
      )}
      {/* COOP-053 不假装这是法律意见 */}
      <p className="muted" data-testid="compliance-disclaimer" style={{ marginTop: 8 }}>
        {path.disclaimer}
      </p>
    </div>
  );
}
