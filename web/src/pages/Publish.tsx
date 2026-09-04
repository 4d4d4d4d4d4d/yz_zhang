import { ApiError, fmtYuan, type Decomposition, type PriceReference, type Task } from '@platform/core';
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useApp } from '../store';

type Feasibility = { level: string; message: string } | null;

export default function Publish() {
  const { client } = useApp();
  const nav = useNavigate();
  const [form, setForm] = useState({
    title: '', description: '', category: '保洁', budget_yuan: '200',
    task_type: 'service', pricing: 'fixed', recurrence: 'none',
    people_needed: '1', deposit_yuan: '0', is_remote: false, city: '上海',
    lat: '31.2304', lng: '121.4737', address_hint: '', address_exact: '',
  });
  const [categories, setCategories] = useState<Array<{ name: string; required_cert: string }>>([]);
  const [cities, setCities] = useState<string[]>([]);
  const [checklist, setChecklist] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [priceRef, setPriceRef] = useState<PriceReference | null>(null);
  const [feasibility, setFeasibility] = useState<Feasibility>(null);
  // 项目型任务：先创建草稿 → AI 分解 → 编辑确认（AI-DEC-010/011）
  const [parent, setParent] = useState<Task | null>(null);
  const [dec, setDec] = useState<Decomposition | null>(null);

  const set = (k: string, v: string | boolean) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    void client.categories().then(setCategories).catch(() => {});
    void client.cities().then((rows) => setCities(rows.map((c) => c.name))).catch(() => {});
  }, [client]);

  // TASK-003 模板填充
  async function applyTemplate() {
    try {
      const tpl = await client.taskTemplate(form.category);
      setForm((f) => ({ ...f, title: tpl.title, description: tpl.description }));
      setChecklist(tpl.checklist);
      setPriceRef(tpl.price_reference);
    } catch {
      setChecklist([]);
      setError('该类目暂无模板');
    }
  }

  async function checkPrice() {
    setPriceRef(await client.priceReference(form.category, form.city || undefined));
  }

  // AI-DEC-001/002 澄清与可行性（失焦时轻量调用）
  async function runClarify() {
    const res = await client.clarify({
      title: form.title, description: form.description, category: form.category,
      budget_cents: Math.round(parseFloat(form.budget_yuan || '0') * 100),
      city: form.city, is_remote: form.is_remote,
    }).catch(() => null);
    if (res) setFeasibility(res.feasibility);
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
        pricing: form.pricing,
        recurrence: form.recurrence,
        people_needed: parseInt(form.people_needed, 10) || 1,
        deposit_cents: Math.round(parseFloat(form.deposit_yuan || '0') * 100),
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
                  await client.confirmDecomposition(dec.id);
                  nav(`/tasks/${parent.id}`);
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
        <div className="row">
          <h3 className="grow">发布任务</h3>
          <button type="button" className="ghost" onClick={() => void applyTemplate()}>📋 用类目模板填充</button>
        </div>
        {checklist.length > 0 && (
          <p className="muted">避坑清单：{checklist.join('；')}</p>
        )}
        <form className="form" onSubmit={submit}>
          <label>标题<input value={form.title} onChange={(e) => set('title', e.target.value)} required minLength={2} /></label>
          <label>描述<textarea rows={3} value={form.description} onChange={(e) => set('description', e.target.value)} /></label>
          <div className="row">
            <label className="grow">类目
              <select value={form.category} onChange={(e) => set('category', e.target.value)}>
                {(categories.length ? categories.map((c) => c.name) : ['保洁']).map((c) => <option key={c}>{c}</option>)}
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
          {categories.find((c) => c.name === form.category)?.required_cert && (
            <p className="muted">⚠️ 该类目为受限类目，仅持「{categories.find((c) => c.name === form.category)!.required_cert}」资质的执行者可接单</p>
          )}
          <div className="row">
            <label className="grow">预算（元）
              <input type="number" min={1} value={form.budget_yuan}
                     onChange={(e) => set('budget_yuan', e.target.value)} onBlur={() => void runClarify()} />
            </label>
            <label className="grow">计价方式
              <select value={form.pricing} onChange={(e) => set('pricing', e.target.value)}>
                <option value="fixed">一口价</option>
                <option value="bidding">竞价（执行者报价比选）</option>
              </select>
            </label>
            <button type="button" className="ghost" onClick={() => void checkPrice()}>查参考价</button>
          </div>
          {feasibility && feasibility.level !== 'no_data' && (
            <p className={feasibility.level === 'ok' ? 'muted' : 'error'}>🤖 {feasibility.message}</p>
          )}
          {priceRef && (
            <p className="muted">
              {priceRef.sample_size > 0
                ? `同类闭环任务 ${priceRef.sample_size} 单：中位价 ${fmtYuan(priceRef.p50_cents!)}（${fmtYuan(priceRef.min_cents!)} ~ ${fmtYuan(priceRef.max_cents!)}）`
                : priceRef.message}
            </p>
          )}
          <div className="row">
            <label className="grow">需要人数（&gt;1 自动拆名额）
              <input type="number" min={1} max={50} value={form.people_needed} onChange={(e) => set('people_needed', e.target.value)} />
            </label>
            <label className="grow">执行者保证金（元，0=不要求）
              <input type="number" min={0} value={form.deposit_yuan} onChange={(e) => set('deposit_yuan', e.target.value)} />
            </label>
            <label className="grow">周期
              <select value={form.recurrence} onChange={(e) => set('recurrence', e.target.value)}>
                <option value="none">一次性</option>
                <option value="weekly">每周（完成自动续期）</option>
                <option value="monthly">每月</option>
              </select>
            </label>
          </div>
          <label className="row" style={{ display: 'flex' }}>
            <input type="checkbox" style={{ width: 'auto' }} checked={form.is_remote} onChange={(e) => set('is_remote', e.target.checked)} />
            线上任务（可远程完成，不限地域）
          </label>
          {!form.is_remote && (
            <>
              <div className="row">
                <label className="grow">城市（仅开通城市可发布线下任务）
                  <select value={form.city} onChange={(e) => set('city', e.target.value)}>
                    {(cities.length ? cities : ['上海']).map((c) => <option key={c}>{c}</option>)}
                  </select>
                </label>
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
