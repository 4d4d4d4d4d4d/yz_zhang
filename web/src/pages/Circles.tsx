import { ApiError, TASK_STATUS_LABEL, fmtYuan, type CircleInfo, type ContentItem, type Task } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useApp } from '../store';

export default function Circles() {
  const { client } = useApp();
  const [circles, setCircles] = useState<CircleInfo[]>([]);
  const [active, setActive] = useState<CircleInfo | null>(null);
  const [feed, setFeed] = useState<ContentItem[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [postBody, setPostBody] = useState('');
  const [error, setError] = useState('');
  const [form, setForm] = useState({ name: '', kind: 'interest', skill_tag: '', city: '', join_policy: 'open' });
  const [showCreate, setShowCreate] = useState(false);

  const load = useCallback(async () => setCircles(await client.circles()), [client]);
  useEffect(() => { void load(); }, [load]);

  async function open(c: CircleInfo) {
    setActive(c);
    setError('');
    if (c.my_status === 'active') {
      setFeed(await client.circleFeed(c.id).catch(() => []));
      setTasks(await client.circleTasks(c.id).catch(() => []));
    } else {
      setFeed([]);
      setTasks([]);
    }
  }

  async function act(fn: () => Promise<unknown>) {
    setError('');
    try {
      await fn();
      await load();
      if (active) await open(await client.getCircle(active.id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '网络错误');
    }
  }

  return (
    <div className="page" style={{ display: 'grid', gridTemplateColumns: '300px 1fr' }}>
      <div style={{ display: 'grid', gap: 12, alignContent: 'start' }}>
        <div className="card">
          <div className="row">
            <h3 className="grow">圈层</h3>
            <button className="ghost" onClick={() => setShowCreate(!showCreate)}>＋创建</button>
          </div>
          {showCreate && (
            <div className="form" style={{ marginTop: 8 }}>
              <input placeholder="圈层名称" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                <option value="interest">兴趣圈</option>
                <option value="skill">能力圈</option>
                <option value="local">地域圈</option>
              </select>
              {form.kind === 'skill' && (
                <input placeholder="绑定技能标签（如：保洁）" value={form.skill_tag} onChange={(e) => setForm({ ...form, skill_tag: e.target.value })} />
              )}
              {form.kind === 'local' && (
                <input placeholder="绑定城市" value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} />
              )}
              <select value={form.join_policy} onChange={(e) => setForm({ ...form, join_policy: e.target.value })}>
                <option value="open">开放加入</option>
                <option value="approval">申请审核</option>
              </select>
              <button onClick={() => act(async () => {
                await client.createCircle(form);
                setShowCreate(false);
              })}>创建圈层</button>
            </div>
          )}
          <div className="list" style={{ marginTop: 8 }}>
            {circles.map((c) => (
              <a key={c.id} onClick={() => void open(c)} style={{ cursor: 'pointer' }}>
                {c.kind === 'skill' ? '🛠' : c.kind === 'local' ? '📍' : '⭐'} {c.name}
                <span className="muted"> · {c.member_count} 人</span>
              </a>
            ))}
          </div>
        </div>
      </div>
      <div style={{ display: 'grid', gap: 12, alignContent: 'start' }}>
        {!active && <div className="card muted">选择或创建一个圈层</div>}
        {active && (
          <>
            <div className="card">
              <div className="row">
                <h3 className="grow">{active.name}</h3>
                {active.my_status === null && (
                  <button onClick={() => act(() => client.joinCircle(active.id))}>
                    {active.join_policy === 'open' ? '加入圈层' : '申请加入'}
                  </button>
                )}
                {active.my_status === 'pending' && <span className="badge warn">待审核</span>}
                {active.my_role === 'owner' && <span className="badge">圈主</span>}
              </div>
              <p className="muted">{active.description || `${active.member_count} 位成员`}
                {active.min_credit > 0 && ` · 信用分 ≥ ${active.min_credit}`}</p>
              {error && <p className="error">{error}</p>}
            </div>
            {active.my_status === 'active' && (
              <>
                <div className="card">
                  <h3>圈内任务板</h3>
                  <div className="list" style={{ marginTop: 8 }}>
                    {tasks.length === 0 && <p className="muted">圈内暂无任务。发布任务时选「仅圈层可见」即可定向发到这里。</p>}
                    {tasks.map((t) => (
                      <div className="task-item" key={t.id}>
                        <Link to={`/tasks/${t.id}`}>{t.title}</Link>
                        <span><span className="price">{fmtYuan(t.budget_cents)}</span> <span className="badge">{TASK_STATUS_LABEL[t.status]}</span></span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="card">
                  <h3>圈内动态</h3>
                  <div className="row" style={{ margin: '8px 0' }}>
                    <input className="grow" placeholder="发圈内帖…" value={postBody} onChange={(e) => setPostBody(e.target.value)} />
                    <button disabled={!postBody.trim()} onClick={() => act(async () => {
                      await client.createContent({ body: postBody, circle_id: active.id, visibility: 'circle' });
                      setPostBody('');
                    })}>发布</button>
                  </div>
                  {feed.map((c) => (
                    <p key={c.id} style={{ borderTop: '1px solid var(--line)', padding: '8px 0' }}>
                      <strong>{c.author_nickname}</strong>：{c.body}
                    </p>
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
