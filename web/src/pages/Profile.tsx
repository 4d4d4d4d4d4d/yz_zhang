import { ApiError, fmtYuan, type InvitationItem } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
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
            <span className="muted">{s.device.slice(0, 60) || '未知设备'} · {new Date(s.created_at).toLocaleString()}</span>
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
      setError(err instanceof ApiError ? err.message : '网络错误');
    }
  }

  return (
    <div className="page">
      <div className="card">
        <h3>{me.nickname} {me.is_verified ? <span className="badge ok">已实名</span> : <span className="badge warn">未实名</span>}</h3>
        <p className="muted">信用分 {me.credit_score} · 评分 {me.rating_avg || '暂无'} · 已完成 {me.tasks_completed} 单 · {me.city || '未设置城市'}</p>
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
      <ServicePricing />
      <DeviceSessions />
      <div className="card row">
        <button className="danger" onClick={() => { setToken(null); nav('/'); }}>退出登录</button>
        <button className="ghost" onClick={async () => {
          if (!confirm('注销后账号不可恢复（需先结清合约与余额），确认继续？')) return;
          try {
            await client.deactivateAccount();
            setToken(null);
            nav('/');
          } catch (err) {
            setError(err instanceof ApiError ? err.message : '注销失败');
          }
        }}>注销账号</button>
        {error && <p className="error">{error}</p>}
      </div>
    </div>
  );
}
