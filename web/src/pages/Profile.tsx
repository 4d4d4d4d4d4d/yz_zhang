import { apiErrorText, fmtYuan, formatDateTime, type AgreementStatus, type CertificationApplicationView, type InvitationItem } from '@platform/core';
import { compressToBase64 } from '../PhotoPicker';
import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useApp } from '../store';

function ServicePricing() {
  const { client, me, refreshMe } = useApp();
  const [rate, setRate] = useState('');
  const [times, setTimes] = useState('');
  const [pub, setPub] = useState(true);
  const [msg, setMsg] = useState('');
  if (!me) return null;
  return (
    <div className="card">
      <h3>服务设置与隐私</h3>
      <div className="row" style={{ marginTop: 8 }}>
        <label className="grow">服务定价（元/次，0=面议）
          <input type="number" min={0} value={rate} placeholder="80" onChange={(e) => setRate(e.target.value)} />
        </label>
        <label className="grow">可接单时间
          <input value={times} placeholder="工作日晚间/周末全天" onChange={(e) => setTimes(e.target.value)} />
        </label>
      </div>
      <label className="row" style={{ display: 'flex', marginTop: 8 }}>
        <input type="checkbox" style={{ width: 'auto' }} checked={pub} onChange={(e) => setPub(e.target.checked)} />
        公开我的完整名片（关闭后他人仅可见信用摘要）
      </label>
      <button style={{ marginTop: 8 }} onClick={async () => {
        await client.updateMe({
          service_rate_cents: Math.round(parseFloat(rate || '0') * 100),
          available_times: times,
          privacy: { profile_public: pub },
        });
        await refreshMe();
        setMsg('已保存');
      }}>保存</button>
      {msg && <span style={{ color: 'var(--ok)', marginLeft: 8 }}>{msg}</span>}
    </div>
  );
}

/** ACC-040 修改密码。服务端 `changePassword` / `resetPassword` 一直都在，
 *  **两端都没有入口**——用户怀疑密码泄露时，能做的只有注销账号。
 *
 *  改完服务端会换发 token（旧的失效），所以这里把新 token 换上，
 *  否则用户会莫名其妙被登出。 */
function ChangePassword() {
  const { client, setToken } = useApp();
  const [oldPw, setOldPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');
  return (
    <div className="card">
      <h3>修改密码</h3>
      <div className="row">
        <input type="password" placeholder="当前密码" value={oldPw}
               onChange={(e) => setOldPw(e.target.value)} />
        <input type="password" placeholder="新密码（至少 8 位）" value={newPw}
               onChange={(e) => setNewPw(e.target.value)} />
        <button disabled={!oldPw || newPw.length < 8} onClick={async () => {
          setMsg(''); setError('');
          try {
            const r = await client.changePassword(oldPw, newPw);
            setToken(r.token);          // 服务端换发的新 token
            setOldPw(''); setNewPw('');
            setMsg('密码已修改，其他设备上的登录态已失效');
          } catch (err) {
            setError(apiErrorText(err));
          }
        }}>确认修改</button>
      </div>
      {msg && <p className="muted">{msg}</p>}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

/** TASK-065 我的报名。接口有、分页测过、**两端都没有界面**——
 *  报完名，用户在产品里找不到自己报过哪些单，只能回广场一个个翻。 */
function MyApplications() {
  const { client } = useApp();
  const [rows, setRows] = useState<Awaited<ReturnType<typeof client.myApplications>>>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setRows(await client.myApplications({ limit: 50 }).catch(() => []));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  if (rows.length === 0) return null;
  return (
    <div className="card">
      <h3>我的报名（{rows.length}）</h3>
      <div className="list" style={{ marginTop: 8 }}>
        {rows.map((r) => (
          <div className="task-item" key={r.application_id}>
            <div>
              <Link to={`/tasks/${r.task_id}`}>{r.task_title ?? `任务 #${r.task_id}`}</Link>
              <p className="muted">
                {r.task_budget_cents !== null ? fmtYuan(r.task_budget_cents) : '—'} ·
                我的报价 {fmtYuan(r.bid_cents)} · {r.status}
                {r.task_status ? ` · 任务 ${r.task_status}` : ''}
              </p>
            </div>
            {r.status === 'pending' && (
              <button className="ghost" disabled={busy} style={{ padding: '2px 10px' }}
                      onClick={async () => {
                        setBusy(true);
                        try { await client.withdrawApplication(r.application_id); await load(); }
                        finally { setBusy(false); }
                      }}>撤回报名</button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function DeviceSessions() {
  const { client } = useApp();
  const [sessions, setSessions] = useState<Array<{ id: number; device: string; created_at: string }>>([]);
  const load = useCallback(async () => setSessions(await client.mySessions().catch(() => [])), [client]);
  useEffect(() => { void load(); }, [load]);
  if (sessions.length === 0) return null;
  return (
    <div className="card">
      <h3>登录设备（{sessions.length}）</h3>
      <div className="list" style={{ marginTop: 8 }}>
        {sessions.map((s) => (
          <div className="task-item" key={s.id}>
            <span className="muted">{s.device.slice(0, 60) || '未知设备'} · {formatDateTime(s.created_at)}</span>
            <button className="ghost" style={{ padding: '2px 10px' }}
                    onClick={async () => { await client.revokeSession(s.id); await load(); }}>
              下线
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function PrivacyConsents() {
  const { client } = useApp();
  const [status, setStatus] = useState<AgreementStatus | null>(null);
  const [msg, setMsg] = useState('');
  const load = useCallback(
    async () => setStatus(await client.myAgreements().catch(() => null)),
    [client],
  );
  useEffect(() => { void load(); }, [load]);
  if (!status) return null;

  const stale = status.documents.filter((d) => d.needs_reconsent);
  return (
    <div className="card">
      <h3>协议与个人信息授权</h3>
      <p className="muted" style={{ marginTop: 4 }}>当前协议版本 {status.current_version}</p>
      {stale.length > 0 && (
        <div style={{ marginTop: 8 }}>
          {/* LAW-030 协议更新后，发布/接单/资金操作会被拦下，所以这里要显眼 */}
          <p className="error">《{stale.map((d) => d.name).join('、')}》已更新，需重新阅读并同意后才能继续发布任务、接单与资金操作。</p>
          <button onClick={async () => {
            await client.acceptAgreements();
            await load();
            setMsg('已同意最新版本');
          }}>阅读并同意最新版本</button>
        </div>
      )}
      <div className="list" style={{ marginTop: 8 }}>
        {status.sensitive_scopes.map((s) => (
          <div className="task-item" key={s.key}>
            <div>
              <strong>{s.purpose}</strong>
              {' '}
              {s.granted
                ? <span className="badge ok">已授权</span>
                : <span className="badge warn">未授权</span>}
              {/* LAW-032 撤回的后果必须在点之前就看得见 */}
              <p className="muted">{s.revocation_effect}</p>
            </div>
            <button className={s.granted ? 'ghost' : ''} onClick={async () => {
              if (s.granted && !confirm(`撤回后：${s.revocation_effect}\n\n确认撤回？`)) return;
              const res = s.granted
                ? await client.revokeConsent(s.key)
                : await client.grantConsent(s.key);
              await load();
              setMsg(s.granted ? `已撤回（${(res as { applied?: string[] }).applied?.join('、') || '已生效'}）` : '已授权');
            }}>{s.granted ? '撤回同意' : '授权'}</button>
          </div>
        ))}
      </div>
      {msg && <p style={{ color: 'var(--ok)', marginTop: 6 }}>{msg}</p>}
      <p className="muted" style={{ marginTop: 8 }}>
        你还可以
        <button className="ghost" style={{ marginLeft: 6 }} onClick={async () => {
          const data = await client.exportMyData();
          const url = URL.createObjectURL(
            new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
          );
          const a = document.createElement('a');
          a.href = url; a.download = 'my-data.json'; a.click();
          URL.revokeObjectURL(url);
        }}>导出我的全部数据</button>
        （含同意记录）。删除个人信息请使用页面底部的「注销账号」。
      </p>
    </div>
  );
}

export default function Profile() {
  const { client, me, refreshMe, setToken } = useApp();
  const nav = useNavigate();
  const [skills, setSkills] = useState(me?.skills.join('、') ?? '');
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');
  const [invitations, setInvitations] = useState<InvitationItem[]>([]);

  useEffect(() => {
    void client.myInvitations().then(setInvitations).catch(() => {});
  }, [client]);

  if (!me) return <div className="page"><p className="muted">加载中…</p></div>;

  async function act(fn: () => Promise<unknown>, ok: string) {
    setError(''); setMsg('');
    try {
      await fn();
      await refreshMe();
      setMsg(ok);
    } catch (err) {
      setError(apiErrorText(err));
    }
  }

  return (
    <div className="page">
      <div className="card">
        <h3>{me.nickname} {me.is_verified ? <span className="badge ok">已实名</span> : <span className="badge warn">未实名</span>}</h3>
        <p className="muted">信用分 {me.credit_score} · 评分 {me.rating_avg || '暂无'} · 已完成 {me.tasks_completed} 单 · {me.city || '未设置城市'}</p>
        <p className="muted">
          <Link to="/developer">开发者设置</Link>（API 密钥与 Webhook） ·{' '}
          <Link to="/ventures">我的合作体</Link> · <Link to="/teams">我的团队</Link>
        </p>
        {!me.is_verified && (
          <div style={{ marginTop: 12 }}>
            <p className="muted">接单与提现需先实名认证（模拟 eKYC，任意合法格式即可通过）</p>
            <button style={{ marginTop: 6 }} onClick={() => {
              const name = prompt('真实姓名：');
              const idNo = prompt('身份证号：', '110101199001011234');
              if (name && idNo) void act(() => client.verifyIdentity(name, idNo), '实名认证成功');
            }}>去实名认证</button>
          </div>
        )}
      </div>
      <div className="card">
        <h3>技能标签（用于 AI 推荐接单）</h3>
        <div className="row" style={{ marginTop: 8 }}>
          <input className="grow" value={skills} onChange={(e) => setSkills(e.target.value)} placeholder="用、分隔，如：保洁、跑腿" />
          <button onClick={() => act(
            () => client.updateMe({ skills: skills.split(/[、,，\s]+/).filter(Boolean) }), '技能已更新',
          )}>保存</button>
        </div>
        <p className="muted" style={{ marginTop: 6 }}>设置定位城市可提升附近任务匹配：
          <button className="ghost" style={{ marginLeft: 8 }} onClick={() => {
            navigator.geolocation?.getCurrentPosition((pos) =>
              void act(() => client.updateMe({ lat: pos.coords.latitude, lng: pos.coords.longitude }), '定位已更新'));
          }}>使用当前定位</button>
        </p>
        {msg && <p style={{ color: 'var(--ok)' }}>{msg}</p>}
        {error && <p className="error">{error}</p>}
      </div>
      {invitations.filter((i) => i.status === 'pending').length > 0 && (
        <div className="card">
          <h3>收到的任务邀约</h3>
          <div className="list" style={{ marginTop: 8 }}>
            {invitations.filter((i) => i.status === 'pending').map((inv) => (
              <div className="task-item" key={inv.id}>
                <div>
                  <strong>{inv.task_title}</strong> <span className="price">{fmtYuan(inv.budget_cents)}</span>
                  <p className="muted">{inv.message}</p>
                </div>
                <span className="row">
                  <button onClick={async () => {
                    const res = await client.acceptInvitation(inv.id).catch((e) => { setError(e.message); return null; });
                    if (res) nav(`/tasks/${res.task_id}`);
                  }}>接受</button>
                  <button className="ghost" onClick={async () => {
                    await client.declineInvitation(inv.id);
                    setInvitations(await client.myInvitations());
                  }}>婉拒</button>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
      <MyCertifications />
      <ServicePricing />
      <MyApplications />
      <PrivacyConsents />
      <ChangePassword />
      <DeviceSessions />
      <div className="card row">
        <button className="danger" onClick={() => { setToken(null); nav('/'); }}>退出登录</button>
        <button className="ghost" onClick={async () => {
          // ACCDEL-010 闸门看的是钱包三态之和，文案就得说全三态：
          // 「余额」只说了可用态，用户看到「余额 0 却注销不了」会以为是 bug
          if (!confirm(
            '注销后账号不可恢复，且需先结清合约与钱包内全部资金'
            + '（可用余额、合约托管、提现复核冻结）。确认继续？',
          )) return;
          try {
            await client.deactivateAccount();
            setToken(null);
            nav('/');
          } catch (err) {
            setError(apiErrorText(err));
          }
        }}>注销账号</button>
        {error && <p className="error">{error}</p>}
      </div>
    </div>
  );
}

/** CERT-033 职业资质：提交与我的资质（77 号 spec）。
 *
 * V76 把「自己填就算」改成了「核过才算」，V101 给运营补了核验台——
 * 而**两端都没有提交入口**：那个队列会一直是空的，
 * 受限类目对所有人永久关闭。我上一批给出口装了门，而没有人进得来。
 */
function MyCertifications() {
  const { client } = useApp();
  // 用共享类型，不自己另写一份行内类型——上一批就是这么把
  // `decision_reason` 猜成 `reason` 的（V95 那一类）
  const [rows, setRows] = useState<CertificationApplicationView[]>([]);
  const [active, setActive] = useState<string[]>([]);
  const [form, setForm] = useState({ name: '', holderName: '', certNumber: '', issuer: '', expiresAt: '' });
  const [images, setImages] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');

  const load = useCallback(async () => {
    const r = await client.myCertifications().catch(() => null);
    setRows(r?.applications ?? []);
    setActive(r?.active ?? []);
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function pick(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true); setError('');
    try {
      const out: string[] = [];
      for (const f of Array.from(files)) {
        const { contentType, data } = await compressToBase64(f);
        // 资质提交要的是**文件名**（服务端据此发鉴权 URL 给审核员），
        // 不是可匿名访问的图床地址（37 号 spec）
        out.push((await client.uploadImage(contentType, data)).ref);
      }
      setImages([...images, ...out]);
    } catch (err) {
      setError(apiErrorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    setError(''); setMsg('');
    try {
      await client.submitCertification({
        name: form.name, holderName: form.holderName, certNumber: form.certNumber,
        issuer: form.issuer || undefined,
        expiresAt: form.expiresAt || null,
        images,
      });
      setMsg('已提交，等待平台核验');
      setForm({ name: '', holderName: '', certNumber: '', issuer: '', expiresAt: '' });
      setImages([]);
      await load();
    } catch (err) {
      setError(apiErrorText(err));
    }
  }

  return (
    <div className="card">
      <h3>职业资质</h3>
      <p className="muted">
        受限类目（如电工、家政上门）需要先核过资质才能接单。
        {active.length > 0 && ` 当前有效：${active.join('、')}`}
      </p>
      <div className="form" style={{ marginTop: 8 }}>
        <input placeholder="资质名称（如 电工证）" value={form.name}
               onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input placeholder="持证人姓名（须与实名一致）" value={form.holderName}
               onChange={(e) => setForm({ ...form, holderName: e.target.value })} />
        <input placeholder="证书编号" value={form.certNumber}
               onChange={(e) => setForm({ ...form, certNumber: e.target.value })} />
        <input placeholder="发证机关（可选）" value={form.issuer}
               onChange={(e) => setForm({ ...form, issuer: e.target.value })} />
        <input type="date" value={form.expiresAt}
               onChange={(e) => setForm({ ...form, expiresAt: e.target.value })} />
        <input type="file" accept="image/*" multiple onChange={(e) => void pick(e.target.files)} />
        <p className="muted">已选证件影像 {images.length} 张（证件影像仅审核员可见）。</p>
        {error && <p className="error">{error}</p>}
        {msg && <p className="muted" data-testid="cert-submitted">{msg}</p>}
        <button disabled={busy || !form.name || !form.holderName || !form.certNumber || images.length === 0}
                onClick={() => void submit()}>提交核验</button>
      </div>
      {rows.length > 0 && (
        <div className="list" style={{ marginTop: 12 }}>
          {rows.map((r) => (
            <div className="task-item" key={r.id} data-testid={`my-cert-${r.id}`}>
              <div>
                <strong>{r.name}</strong> · 提交于 {formatDateTime(r.created_at)}
                {/* 驳回理由必须显示出来：V101 让运营必须写，写了却看不见，
                    那条强制就只是给运营加了道手续 */}
                <p className="muted">
                  {r.status}{r.decision_reason && ` · ${r.decision_reason}`}
                  {r.expires_at && ` · 有效期至 ${formatDateTime(r.expires_at)}`}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
