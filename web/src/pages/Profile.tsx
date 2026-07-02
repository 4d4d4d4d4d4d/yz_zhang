import { ApiError } from '@platform/core';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApp } from '../store';

export default function Profile() {
  const { client, me, refreshMe, setToken } = useApp();
  const nav = useNavigate();
  const [skills, setSkills] = useState(me?.skills.join('、') ?? '');
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');

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
      <div className="card row">
        <button className="danger" onClick={() => { setToken(null); nav('/'); }}>退出登录</button>
      </div>
    </div>
  );
}
