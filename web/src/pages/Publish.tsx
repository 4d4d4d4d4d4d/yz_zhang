import { apiErrorText, IP_ASSIGNMENT_LABEL, dayLabel, dayShiftsPayload, fmtYuan, localInputToServerTime, type IpAssignment, type PriceReference, type Task } from '@platform/core';
import { DraftHints } from '../Profiles';
import { useEffect, useState, type FormEvent } from 'react';
import type { DayShiftInput } from '@platform/core';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useApp } from '../store';

type Feasibility = { level: string; message: string } | null;

export default function Publish() {
  const { client, me } = useApp();
  const nav = useNavigate();
  // LAW-051 别处把人送到这里时会带上类目（问答答不了 → 「发一单法律咨询」）。
  // 不读这个参数的话，那个补救入口就是**假的**：它看起来把人送到了发布页，
  // 而人到了之后类目仍停在默认的「保洁」上——他得自己想起来再去下拉里找一遍。
  const [params] = useSearchParams();
  // SCN-127（201 号 spec）多天单每天不同时段：勾上才出现每天一行
  const [perDay, setPerDay] = useState(false);
  const [dayRows, setDayRows] = useState<DayShiftInput[]>([]);
  const [form, setForm] = useState({
    // PWB-008 从个人工作台「找人一起做」过来时带着标题和说明
    title: params.get('title') || '', description: params.get('description') || '', // TASK-090 类目与城市**不替人选**：V140 真浏览器演示里，发一个「咖啡店品牌升级」项目，
    // 默认值把它发成了「保洁 · 上海」。带着参数来的（补救入口、模板）照用参数
    category: params.get('category') || '', budget_yuan: '200',
    task_type: 'service', pricing: 'fixed', recurrence: 'none',
    people_needed: '1', days: '1', start_date: '', shift_start: '', shift_end: '', deposit_yuan: '0', is_remote: false, city: params.get('city') || '',
    lat: '31.2304', lng: '121.4737', address_hint: '', address_exact: '',
    // SCN-119（175 号 spec）替别人发单：替谁、到场联系谁、问过本人没有
    on_behalf: false, recipient_label: '', onsite_contact: '', recipient_consented: false,
    // SCN-120（176 号 spec）一单多次上门：上门几次、每次要做的事（顿号或逗号分开）
    visits_planned: '', visit_checklist: '',
    // TZ-064 截止时间此前**网页上根本没有地方填**：服务端有校验、有到期下架 job、
    // 有临期提醒，而线上所有任务的 deadline 都是空的，那个 job 从来没有活可干。
    deadline_local: '',
    // IPC-001 **没有默认值**——留空时服务端会拒绝，这是有意的：
    // 替发布方猜归属，对执行方不公平，对含第三方素材的交付物直接就是错的。
    ip_assignment: '',
  });
  const [categories, setCategories] = useState<Array<{ name: string; required_cert: string }>>([]);
  const [cities, setCities] = useState<string[]>([]);
  const [checklist, setChecklist] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [priceRef, setPriceRef] = useState<PriceReference | null>(null);
  const [feasibility, setFeasibility] = useState<Feasibility>(null);

  const set = (k: string, v: string | boolean) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    void client.categories().then(setCategories).catch(() => {});
    void client.cities().then((rows) => {
      const names = rows.map((c) => c.name);
      setCities(names);
      // 资料里填了城市、且这个城市开通了，就用它——这是这个人自己说过的，不是我们猜的
      if (me?.city && names.includes(me.city)) setForm((f) => (f.city ? f : { ...f, city: me.city }));
    }).catch(() => {});
  }, [client, me?.city]);

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
    if (!form.category) { setError('请选择类目'); return; }
    if (!form.is_remote && !form.city) { setError('线下任务请选择城市，或勾选「线上任务」'); return; }
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
        // SCN-107（167 号 spec）连续几天：名额 = 人数 × 天数
        ...((parseInt(form.days, 10) || 1) > 1 ? { days: parseInt(form.days, 10), start_date: form.start_date || null } : {}),
        // SCN-117（178 号 spec）每天几点到几点：写了才带（只写一头时服务端会说清）
        ...(form.shift_start || form.shift_end ? { shift_start: form.shift_start, shift_end: form.shift_end } : {}),
        ...(perDay && (parseInt(form.days, 10) || 1) > 1 && dayShiftsPayload(dayRows, parseInt(form.days, 10))
          ? { day_shifts: dayShiftsPayload(dayRows, parseInt(form.days, 10)) } : {}),
        deposit_cents: Math.round(parseFloat(form.deposit_yuan || '0') * 100),
        ip_assignment: form.ip_assignment as IpAssignment,
        budget_cents: Math.round(parseFloat(form.budget_yuan) * 100),
        is_remote: form.is_remote,
        city: form.city,
        lat: form.is_remote ? null : parseFloat(form.lat),
        lng: form.is_remote ? null : parseFloat(form.lng),
        address_hint: form.address_hint,
        address_exact: form.address_exact,
        // SCN-120 写了才带：上门几次、每次要做的事
        ...((parseInt(form.visits_planned, 10) || 0) > 0 ? { visits_planned: parseInt(form.visits_planned, 10) } : {}),
        ...(form.visit_checklist.trim() ? { visit_checklist: form.visit_checklist.split(/[、,，]/).map((x) => x.trim()).filter(Boolean) } : {}),
        // SCN-119 只有勾了「替别人发」才带这几项（服务端对没勾却带了的会拒）
        ...(form.on_behalf ? { on_behalf: true, recipient_label: form.recipient_label, onsite_contact: form.onsite_contact,
          recipient_consented: form.recipient_consented } : {}),
        // TZ-063 发出去的是**带偏移**的 ISO：datetime-local 给的是没有偏移的
        // 本地字符串，直发的话服务端会当 UTC，差一个时区
        ...(form.deadline_local ? { deadline: localInputToServerTime(form.deadline_local) } : {}),
        publish_now: !isProject,
      });
      if (isProject) {
        // 项目型任务：先存草稿，再到拆解页一层一层拆（AI-DEC-041，106 号 spec）
        nav(`/tasks/${task.id}/decompose`);
      } else {
        nav(`/tasks/${task.id}`);
      }
    } catch (err) {
      setError(apiErrorText(err));
    }
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
        {/* PROF-101 边写边提示还缺什么（126 号 spec） */}
        <DraftHints draft={{
          title: form.title, description: form.description, category: form.category,
          budget_cents: Math.round(Number(form.budget_yuan || 0) * 100), is_remote: form.is_remote, city: form.city,
          lat: form.is_remote ? null : Number(form.lat), deadline: form.deadline_local ? localInputToServerTime(form.deadline_local) : null,
        }} />
        <form className="form" onSubmit={submit}>
          <label>标题<input value={form.title} onChange={(e) => set('title', e.target.value)} required minLength={2} /></label>
          <label>描述<textarea rows={3} value={form.description} onChange={(e) => set('description', e.target.value)} /></label>
          <div className="row">
            <label className="grow">类目
              <select value={form.category} onChange={(e) => set('category', e.target.value)} required>
                <option value="" disabled>请选择类目</option>
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
          {/* IPC-001 知识产权归属：**必选，无默认值**。
              不选的话按《著作权法》第十七条著作权归执行方——
              发布方花钱买的 logo 默认不属于他，而这通常不是他想要的。
              所以这里刻意不预选任何一项，逼一次显式选择。 */}
          <label>交付成果归谁（必选）
            <select value={form.ip_assignment}
                    onChange={(e) => set('ip_assignment', e.target.value)}>
              <option value="">— 请选择 —</option>
              {(Object.keys(IP_ASSIGNMENT_LABEL) as IpAssignment[]).map((k) => (
                <option key={k} value={k}>{IP_ASSIGNMENT_LABEL[k]}</option>
              ))}
            </select>
          </label>
          <p className="muted" style={{ marginTop: -6 }}>
            不约定的话，按《著作权法》著作权默认归执行方；署名权等人身权依法
            不可转让，任何选项下都归作者。
          </p>

          <div className="row">
            <label className="grow">需要人数（&gt;1 自动拆名额）
              <input type="number" min={1} max={50} value={form.people_needed} onChange={(e) => set('people_needed', e.target.value)} />
            </label>
            <label className="grow">连续几天（&gt;1 按天拆名额）
              <input type="number" aria-label="连续几天" min={1} max={14} value={form.days} onChange={(e) => set('days', e.target.value)} />
            </label>
            {/* SCN-117 每天几点到几点（北京时间） */}
            <label className="grow">每天从
              <input type="time" aria-label="每天几点开始" value={form.shift_start} onChange={(e) => set('shift_start', e.target.value)} />
            </label>
            <label className="grow">到
              <input type="time" aria-label="每天几点结束" value={form.shift_end} onChange={(e) => set('shift_end', e.target.value)} />
            </label>
            {(parseInt(form.days, 10) || 1) > 1 && (
              <label className="grow">从哪天开始
                <input type="date" aria-label="从哪天开始" value={form.start_date} onChange={(e) => set('start_date', e.target.value)} />
              </label>
            )}
            {(parseInt(form.days, 10) || 1) > 1 && (
              <label className="row"><input type="checkbox" aria-label="每天时段不一样" checked={perDay} onChange={(e) => setPerDay(e.target.checked)} />
                每天时段不一样（某天空着就用上面的时段）</label>
            )}
            {perDay && (parseInt(form.days, 10) || 1) > 1 && (
              <div aria-label="每天的时段">
                {Array.from({ length: Math.min(parseInt(form.days, 10) || 1, 14) }, (_, i) => (
                  <div className="row" key={i}>
                    <span className="muted">{dayLabel(form.start_date, i)}</span>
                    <input type="time" aria-label={`第 ${i + 1} 天几点开始`} value={dayRows[i]?.start ?? ''}
                           onChange={(e) => setDayRows((rs) => { const n = [...rs]; n[i] = { start: e.target.value, end: n[i]?.end ?? '' }; return n; })} />
                    <input type="time" aria-label={`第 ${i + 1} 天几点结束`} value={dayRows[i]?.end ?? ''}
                           onChange={(e) => setDayRows((rs) => { const n = [...rs]; n[i] = { start: n[i]?.start ?? '', end: e.target.value }; return n; })} />
                  </div>
                ))}
              </div>
            )}
            <label className="grow">执行者保证金（元，0=不要求）
              <input type="number" min={0} value={form.deposit_yuan} onChange={(e) => set('deposit_yuan', e.target.value)} />
            </label>
            <label className="grow">截止时间（可选）
              <input type="datetime-local" value={form.deadline_local}
                     onChange={(e) => set('deadline_local', e.target.value)} />
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
                  <select value={form.city} onChange={(e) => set('city', e.target.value)} required>
                    <option value="" disabled>请选择城市</option>
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
          {/* SCN-120 一单多次上门（176 号 spec）：接单人每次按清单回报 */}
          <div className="row">
            <label className="grow">要上门几次（可不填）
              <input type="number" aria-label="要上门几次" min={0} max={60} value={form.visits_planned}
                     onChange={(e) => set('visits_planned', e.target.value)} />
            </label>
            <label className="grow">每次要做的事（用顿号分开，可不填）
              <input aria-label="每次要做的事" value={form.visit_checklist} placeholder="如：喂食、换水、铲屎"
                     onChange={(e) => set('visit_checklist', e.target.value)} />
            </label>
          </div>
          {/* SCN-119 替别人发单（175 号 spec）：替谁、到场联系谁只给成交双方；发之前先问过本人 */}
          <label className="row">
            <input type="checkbox" aria-label="替别人发" checked={form.on_behalf} onChange={(e) => set('on_behalf', e.target.checked)} />
            替别人发（家人、朋友）
          </label>
          {form.on_behalf && (
            <div aria-label="服务对象">
              <label>服务对象怎么称呼（仅成交后对执行者可见）
                <input aria-label="服务对象称呼" maxLength={20} value={form.recipient_label}
                       onChange={(e) => set('recipient_label', e.target.value)} placeholder="如：我妈、王阿姨" />
              </label>
              <label>到场联系谁（仅成交后可见，结束 30 天后清除）
                <input aria-label="到场联系" maxLength={40} value={form.onsite_contact}
                       onChange={(e) => set('onsite_contact', e.target.value)} placeholder="如：王阿姨 139…" />
              </label>
              <label className="row">
                <input type="checkbox" aria-label="已经问过本人" checked={form.recipient_consented}
                       onChange={(e) => set('recipient_consented', e.target.checked)} />
                已经问过本人，他/她同意有人上门、同意把称呼和联系方式给接单的人
              </label>
              <p className="muted">身份证号、银行卡、验证码不要写在任何地方；钱由你托管、你验收。</p>
            </div>
          )}
          {error && <p className="error">{error}</p>}
          <button type="submit">{form.task_type === 'project' ? '创建并让 AI 分解' : '发布任务'}</button>
        </form>
      </div>
    </div>
  );
}
