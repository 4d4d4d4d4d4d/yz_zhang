import { ApiError, fmtYuan, type Decomposition, type PriceReference, type Task } from '@platform/core';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useApp } from '../store';

export default function Publish() {
  const { client } = useApp();
  const nav = useNavigate();
  const [form, setForm] = useState({
    title: '', description: '', category: '保洁', budget_yuan: '200',
    task_type: 'service', is_remote: false, city: '上海',
    lat: '31.2304', lng: '121.4737', address_hint: '', address_exact: '',
  });
  const [error, setError] = useState('');
  const [priceRef, setPriceRef] = useState<PriceReference | null>(null);
  // 项目型任务：先创建草稿 → AI 分解 → 编辑确认（AI-DEC-010/011）
  const [parent, setParent] = useState<Task | null>(null);
  const [dec, setDec] = useState<Decomposition | null>(null);

  const set = (k: string, v: string | boolean) => setForm((f) => ({ ...f, [k]: v }));

  async function checkPrice() {
    setPriceRef(await client.priceReference(form.category, form.city || undefined));
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError('');
    const isProject = form.task_type === 'project';
    try {
      const task = await client.createTask({
        title: form.title,
        description: form.description,
        category: form.category,
        task_type: form.task_type as Task['task_type'],
        budget_cents: Math.round(parseFloat(form.budget_yuan) * 100),
        is_remote: form.is_remote,
        city: form.city,
        lat: form.is_remote ? null : parseFloat(form.lat),
        lng: form.is_remote ? null : parseFloat(form.lng),
        address_hint: form.address_hint,
        address_exact: form.address_exact,
        publish_now: !isProject,
      });
      if (isProject) {
        setParent(task);
        setDec(await client.propose(task.id));
      } else {
        nav(`/tasks/${task.id}`);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '网络错误');
    }
  }

  async function confirmDec() {
    if (!dec) return;
    try {
      await client.confirmDecomposition(dec.id);
      nav(`/tasks/${parent!.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '网络错误');
    }
  }

  if (parent && dec) {
    return (
      <div className="page">
        <div className="card">
          <h3>AI 任务分解草稿（可编辑后确认）</h3>
          <p className="muted">来源：{dec.source} · 母任务预算 {fmtYuan(parent.budget_cents)} · 确认后无前置依赖的子任务将立即发布</p>
          <table>
            <thead>
              <tr><th>#</th><th>子任务</th><th>技能</th><th>预算</th><th>依赖</th></tr>
            </thead>
            <tbody>
              {dec.items.map((item, i) => (
                <tr key={i}>
                  <td>{i + 1}</td>
                  <td>{item.title}</td>
                  <td className="muted">{item.required_skills.join('、') || '-'}</td>
                  <td>
                    <input
                      style={{ width: 100 }}
                      type="number"
                      value={item.budget_cents / 100}
                      onChange={(e) => {
                        const items = dec.items.map((it, j) =>
                          j === i ? { ...it, budget_cents: Math.round(parseFloat(e.target.value || '0') * 100) } : it,
                        );
                        setDec({ ...dec, items });
                      }}
                    />
                  </td>
                  <td className="muted">{item.depends_on_idx.map((d) => `#${d + 1}`).join(',') || '无'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {error && <p className="error">{error}</p>}
          <div className="row" style={{ marginTop: 12 }}>
            <button
              onClick={async () => {
                try {
                  setDec(await client.editDecomposition(dec.id, dec.items));
                  await confirmDec();
                } catch (err) {
                  setError(err instanceof ApiError ? err.message : '网络错误');
                }
              }}
            >
              确认分解并发布
            </button>
            <Link to="/"><button className="ghost" type="button">稍后处理</button></Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="card">
        <h3>发布任务</h3>
        <form className="form" onSubmit={submit}>
          <label>标题<input value={form.title} onChange={(e) => set('title', e.target.value)} required minLength={2} /></label>
          <label>描述<textarea rows={3} value={form.description} onChange={(e) => set('description', e.target.value)} /></label>
          <div className="row">
            <label className="grow">类目
              <select value={form.category} onChange={(e) => set('category', e.target.value)}>
                {['保洁', '跑腿', '维修', '软件开发', '设计', '活动策划', '二手交易'].map((c) => <option key={c}>{c}</option>)}
              </select>
            </label>
            <label className="grow">类型
              <select value={form.task_type} onChange={(e) => set('task_type', e.target.value)}>
                <option value="service">服务（保洁/跑腿等）</option>
                <option value="trade">交易担保</option>
                <option value="project">项目（AI 帮我分解）</option>
                <option value="event">小事件</option>
              </select>
            </label>
          </div>
          <div className="row">
            <label className="grow">预算（元）<input type="number" min={1} value={form.budget_yuan} onChange={(e) => set('budget_yuan', e.target.value)} /></label>
            <button type="button" className="ghost" onClick={() => void checkPrice()}>查同类参考价</button>
          </div>
          {priceRef && (
            <p className="muted">
              {priceRef.sample_size > 0
                ? `同类闭环任务 ${priceRef.sample_size} 单：中位价 ${fmtYuan(priceRef.p50_cents!)}（${fmtYuan(priceRef.min_cents!)} ~ ${fmtYuan(priceRef.max_cents!)}）`
                : priceRef.message}
            </p>
          )}
          <label className="row" style={{ display: 'flex' }}>
            <input type="checkbox" style={{ width: 'auto' }} checked={form.is_remote} onChange={(e) => set('is_remote', e.target.checked)} />
            线上任务（可远程完成，不限地域）
          </label>
          {!form.is_remote && (
            <>
              <div className="row">
                <label className="grow">城市<input value={form.city} onChange={(e) => set('city', e.target.value)} /></label>
                <label className="grow">纬度<input value={form.lat} onChange={(e) => set('lat', e.target.value)} /></label>
                <label className="grow">经度<input value={form.lng} onChange={(e) => set('lng', e.target.value)} /></label>
              </div>
              <label>商圈（公开显示）<input value={form.address_hint} onChange={(e) => set('address_hint', e.target.value)} placeholder="如：静安寺商圈" /></label>
              <label>详细地址（仅成交后对执行者可见）<input value={form.address_exact} onChange={(e) => set('address_exact', e.target.value)} /></label>
            </>
          )}
          {error && <p className="error">{error}</p>}
          <button type="submit">{form.task_type === 'project' ? '创建并让 AI 分解' : '发布任务'}</button>
        </form>
      </div>
    </div>
  );
}
