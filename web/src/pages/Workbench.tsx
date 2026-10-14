import {
  apiErrorText, fmtYuan, formatDateTime, localInputToServerTime, millisUntil, serverTimeToLocalInput,
  type WbItem, type WbItemDetail, type WbLog, type WbMemory, type WbOverview, type WbProject,
  type AssistantCosts, type WbRoutine, type WbRoutineHealth, type WbRoutineInput, type WbRoutineRun, type WbRunStatus, type WbStatus, type WbStep,
  type NbMethod, type NbReference,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useApp } from '../store';

/** PWB 个人工作台（116 号 spec）：我的任务、进度与助手。
 *
 * 个人门户不只对外展示，也要能管自己的事。参照 WorkBuddy：按项目分组的任务列表、
 * 让助手拆清单（只出草稿）、助手记忆、定时的例行任务。平台上「等我处理的事」也汇总在「今天」里。
 */
const STATUS: [WbStatus, string][] = [['todo', '待办'], ['doing', '进行中'], ['blocked', '卡住'], ['done', '完成'], ['dropped', '放弃']];
const PRIORITY = ['低', '普通', '高', '紧急'];
const SOURCE: Record<string, string> = { manual: '手填', children: '按清单', platform: '跟平台任务' };
type Tab = 'today' | 'all' | 'board' | 'assistant';

export default function Workbench() {
  const { client } = useApp();
  const [params, setParams] = useSearchParams();
  const tab = (params.get('tab') as Tab) || 'today';
  const openId = Number(params.get('item')) || null;
  const [projects, setProjects] = useState<WbProject[]>([]);
  const [error, setError] = useState('');
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => { client.workbenchProjects().then(setProjects).catch((e) => setError(apiErrorText(e))); }, [client, version]);

  function go(next: Partial<{ tab: Tab; item: number | null }>) {
    const p = new URLSearchParams(params);
    if (next.tab) p.set('tab', next.tab);
    if (next.item !== undefined) { if (next.item) p.set('item', String(next.item)); else p.delete('item'); }
    setParams(p);
  }

  return (
    <div className="page workbench">
      <div className="page-heading">
        <h2>我的工作台</h2>
        <p className="muted">自己的任务、进度和助手。这里的东西只有你自己看得到。</p>
      </div>
      <div className="row" role="tablist" aria-label="工作台视图">
        {([['today', '今天'], ['all', '全部'], ['board', '看板'], ['assistant', '助手']] as [Tab, string][]).map(([t, label]) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? '' : 'ghost'} onClick={() => go({ tab: t })}>{label}</button>
        ))}
      </div>
      {error && <p className="error">{error}</p>}
      {tab !== 'assistant' && <QuickAdd projects={projects} onAdded={refresh} />}
      {tab === 'today' && <Today version={version} open={(id) => go({ item: id })} />}
      {tab === 'all' && <AllItems version={version} projects={projects} open={(id) => go({ item: id })} onChanged={refresh} />}
      {tab === 'board' && <Board version={version} open={(id) => go({ item: id })} onChanged={refresh} />}
      {tab === 'assistant' && <Assistant />}
      {openId && <ItemPanel id={openId} projects={projects} onClose={() => go({ item: null })} onChanged={refresh} />}
    </div>
  );
}

function QuickAdd({ projects, onAdded }: { projects: WbProject[]; onAdded: () => void }) {
  const { client } = useApp();
  const [title, setTitle] = useState('');
  const [due, setDue] = useState('');
  const [projectId, setProjectId] = useState('');
  const [newProject, setNewProject] = useState('');
  const [error, setError] = useState('');

  async function add() {
    if (!title.trim()) return;
    setError('');
    try {
      await client.createWorkbenchItem({
        title, project_id: projectId ? Number(projectId) : null,
        due_at: due ? localInputToServerTime(due) : null,
      });
      setTitle(''); setDue('');
      onAdded();
    } catch (e) { setError(apiErrorText(e)); }
  }
  async function addProject() {
    if (!newProject.trim()) return;
    try {
      const p = await client.createWorkbenchProject(newProject);
      setNewProject(''); setProjectId(String(p.id));
      onAdded();
    } catch (e) { setError(apiErrorText(e)); }
  }

  return (
    <div className="card">
      <div className="row">
        <input className="grow" aria-label="新任务" placeholder="要做的事，回车添加" value={title}
               onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && void add()} />
        <input type="datetime-local" aria-label="截止时间" value={due} onChange={(e) => setDue(e.target.value)} />
        <select aria-label="所属项目" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
          <option value="">不归项目</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <button onClick={() => void add()}>添加</button>
      </div>
      <div className="row">
        <input aria-label="新项目名称" placeholder="新建项目（如：装修、报税、副业）" value={newProject}
               onChange={(e) => setNewProject(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && void addProject()} />
        <button className="ghost" onClick={() => void addProject()}>新建项目</button>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function Progress({ item }: { item: WbItem }) {
  return (
    <div title={`进度 ${item.progress}%（${SOURCE[item.progress_source]}）`}>
      <div className="progress-bar" role="progressbar" aria-valuenow={item.progress} aria-valuemin={0} aria-valuemax={100}>
        <div style={{ width: `${item.progress}%` }} />
      </div>
    </div>
  );
}

function ItemRow({ item, open }: { item: WbItem; open: (id: number) => void }) {
  const overdue = !!item.due_at && item.status !== 'done' && millisUntil(item.due_at) < 0;
  return (
    <li className="task-item" data-wb-item={item.id}>
      <button className="text-link" onClick={() => open(item.id)}>{item.title}</button>
      <span className="badge">{item.status_name}</span>
      {item.priority >= 2 && <span className="badge">{PRIORITY[item.priority]}</span>}
      {item.due_at && <span className={overdue ? 'error' : 'muted'}>{overdue ? '已逾期 · ' : '截止 '}{formatDateTime(item.due_at)}</span>}
      {item.children_total > 0 && <span className="muted">清单 {item.children_done}/{item.children_total}</span>}
      {item.linked_task && <span className="muted">平台任务：{item.linked_task.status_name}</span>}
      <Progress item={item} />
    </li>
  );
}

function Today({ version, open }: { version: number; open: (id: number) => void }) {
  const { client } = useApp();
  const [ov, setOv] = useState<WbOverview | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { client.workbenchOverview().then(setOv).catch((e) => setError(apiErrorText(e))); }, [client, version]);
  if (error) return <p className="error">{error}</p>;
  if (!ov) return <p className="muted">正在加载…</p>;
  const sections: [string, WbItem[]][] = [['已逾期', ov.overdue], ['今天到期', ov.today], ['进行中', ov.doing], ['卡住了', ov.blocked],
    ['超过 7 天没动静', ov.stale]];
  const p = ov.platform;
  return (
    <>
      <div className="card"><h3>助手概览</h3><p data-testid="wb-summary">{ov.summary}</p></div>
      {(p.to_choose.length + p.to_accept.length + p.executing.length) > 0 && (
        <div className="card">
          <h3>平台上等我处理的</h3>
          <ul className="list">
            {p.to_choose.map((t) => <li key={`c${t.task_id}`}><Link to={`/tasks/${t.task_id}`}>{t.title}</Link> · {t.applicants} 人报名，等你选人</li>)}
            {p.to_accept.map((t) => <li key={`a${t.task_id}`}><Link to={`/tasks/${t.task_id}`}>{t.title}</Link> · 等你验收</li>)}
            {p.executing.map((t) => <li key={`e${t.task_id}`}><Link to={`/tasks/${t.task_id}`}>{t.title}</Link> · 我在执行（{t.status_name}）</li>)}
          </ul>
        </div>
      )}
      {sections.filter(([, rows]) => rows.length).map(([label, rows]) => (
        <div className="card" key={label}><h3>{label}（{rows.length}）</h3><ul className="list">{rows.map((i) => <ItemRow key={i.id} item={i} open={open} />)}</ul></div>
      ))}
      {ov.counts.open === 0 && <div className="card"><p className="muted">手上没有未完成的事。上面加一条，或者去「助手」里设一个每天早上的概览。</p></div>}
      {ov.projects.length > 0 && (
        <div className="card">
          <h3>项目进度</h3>
          <ul className="list">{ov.projects.map((pr) => (
            <li key={pr.id}>{pr.name} · {pr.done}/{pr.total}
              <div className="progress-bar"><div style={{ width: `${pr.progress}%` }} /></div></li>
          ))}</ul>
        </div>
      )}
    </>
  );
}

function AllItems({ version, projects, open, onChanged }: { version: number; projects: WbProject[]; open: (id: number) => void; onChanged: () => void }) {
  const { client } = useApp();
  const [items, setItems] = useState<WbItem[]>([]);
  const [status, setStatus] = useState<WbStatus | ''>('');
  const [q, setQ] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    client.workbenchItems({ status: status || undefined, q: q || undefined }).then(setItems).catch((e) => setError(apiErrorText(e)));
  }, [client, version, status, q]);
  const groups: [string, WbItem[]][] = [
    ...projects.map((p) => [p.name, items.filter((i) => i.project_id === p.id)] as [string, WbItem[]]),
    ['未归项目', items.filter((i) => !i.project_id || !projects.some((p) => p.id === i.project_id))],
  ];
  async function archive(p: WbProject) {
    try { await client.updateWorkbenchProject(p.id, { archived: true }); onChanged(); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <>
      <div className="row search-toolbar">
        <input className="grow" aria-label="搜索我的任务" placeholder="搜索标题和备注" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="按状态筛选" value={status} onChange={(e) => setStatus(e.target.value as WbStatus | '')}>
          <option value="">全部状态</option>
          {STATUS.map(([s, label]) => <option key={s} value={s}>{label}</option>)}
        </select>
      </div>
      {error && <p className="error">{error}</p>}
      {groups.filter(([, rows]) => rows.length).map(([name, rows]) => {
        const p = projects.find((x) => x.name === name);
        return (
          <div className="card" key={name}>
            <div className="row"><h3 className="grow">{name}（{rows.length}）</h3>
              {p && <button className="ghost" onClick={() => void archive(p)}>归档项目</button>}</div>
            <ul className="list">{rows.map((i) => <ItemRow key={i.id} item={i} open={open} />)}</ul>
          </div>
        );
      })}
      {!items.length && <p className="muted">没有符合条件的任务。</p>}
      {!status && !q && projects.filter((p) => !items.some((i) => i.project_id === p.id)).map((p) => (
        <p key={p.id} className="muted">空项目「{p.name}」
          <button className="ghost" onClick={() => void client.deleteWorkbenchProject(p.id).then(onChanged).catch((e) => setError(apiErrorText(e)))}>删除</button></p>
      ))}
    </>
  );
}

function Board({ version, open, onChanged }: { version: number; open: (id: number) => void; onChanged: () => void }) {
  const { client } = useApp();
  const [items, setItems] = useState<WbItem[]>([]);
  const [error, setError] = useState('');
  useEffect(() => { client.workbenchItems().then(setItems).catch((e) => setError(apiErrorText(e))); }, [client, version]);
  async function move(i: WbItem, status: WbStatus) {
    try { await client.updateWorkbenchItem(i.id, { status, revision: i.revision }); onChanged(); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <>
      {error && <p className="error">{error}</p>}
      <div className="wb-board" aria-label="看板">
        {STATUS.filter(([s]) => s !== 'dropped').map(([s, label]) => (
          <div className="card" key={s} data-column={s}>
            <h3>{label}（{items.filter((i) => i.status === s).length}）</h3>
            <ul className="list">
              {items.filter((i) => i.status === s).map((i) => (
                <li key={i.id}>
                  <button className="text-link" onClick={() => open(i.id)}>{i.title}</button>
                  <div className="row">
                    {STATUS.filter(([t]) => t !== s && t !== 'dropped').map(([t, l]) => (
                      <button key={t} className="ghost" onClick={() => void move(i, t)} aria-label={`把「${i.title}」移到${l}`}>→{l}</button>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </>
  );
}

function ItemPanel({ id, projects, onClose, onChanged }: { id: number; projects: WbProject[]; onClose: () => void; onChanged: () => void }) {
  const { client } = useApp();
  const [item, setItem] = useState<WbItemDetail | null>(null);
  const [logs, setLogs] = useState<WbLog[]>([]);
  const [note, setNote] = useState('');
  const [draft, setDraft] = useState<WbStep[] | null>(null);
  const [refs, setRefs] = useState<NbReference[]>([]);
  const [methods, setMethods] = useState<NbMethod[]>([]);
  const [newStep, setNewStep] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setItem(await client.workbenchItem(id));
      setLogs(await client.workbenchLogs(id));
    } catch (e) { setError(apiErrorText(e)); }
  }, [client, id]);
  useEffect(() => { void load(); }, [load]);
  // KB-104 做这件事时，把自己以前记过的相关笔记与方法摆到眼前（拿不到不影响任务本身）
  useEffect(() => {
    client.relatedNotes(id).then(setRefs).catch(() => setRefs([]));
    client.notebookMethods().then(setMethods).catch(() => setMethods([]));
  }, [client, id]);

  async function patch(p: Parameters<typeof client.updateWorkbenchItem>[1]) {
    if (!item) return;
    setError('');
    try { await client.updateWorkbenchItem(item.id, { ...p, revision: item.revision }); await load(); onChanged(); } catch (e) { setError(apiErrorText(e)); }
  }
  async function act(fn: () => Promise<unknown>) {
    setError('');
    try { await fn(); await load(); onChanged(); } catch (e) { setError(apiErrorText(e)); }
  }
  if (!item) return error ? <p className="error">{error}</p> : null;
  return (
    <div className="card" role="dialog" aria-label={`任务：${item.title}`}>
      <div className="row"><h3 className="grow">{item.title}</h3><button className="ghost" onClick={onClose}>关闭</button></div>
      <div className="row">
        <label>状态 <select value={item.status} onChange={(e) => void patch({ status: e.target.value as WbStatus })}>
          {STATUS.map(([s, l]) => <option key={s} value={s}>{l}</option>)}</select></label>
        <label>优先级 <select value={item.priority} onChange={(e) => void patch({ priority: Number(e.target.value) })}>
          {PRIORITY.map((l, n) => <option key={n} value={n}>{l}</option>)}</select></label>
        <label>项目 <select value={item.project_id ?? ''} onChange={(e) => void patch({ project_id: e.target.value ? Number(e.target.value) : null })}>
          <option value="">不归项目</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      </div>
      <div className="row">
        <label>截止 <input type="datetime-local" defaultValue={serverTimeToLocalInput(item.due_at)}
          onBlur={(e) => void patch({ due_at: e.target.value ? localInputToServerTime(e.target.value) : null })} /></label>
        <label>提醒我 <input type="datetime-local" defaultValue={serverTimeToLocalInput(item.remind_at)}
          onBlur={(e) => void patch({ remind_at: e.target.value ? localInputToServerTime(e.target.value) : null })} /></label>
      </div>
      <p className="muted">进度 {item.progress}%（{SOURCE[item.progress_source]}）</p>
      <Progress item={item} />
      {item.progress_source === 'manual' && (
        <label>手填进度 <input type="range" min={0} max={100} step={10} defaultValue={item.progress}
          aria-label="手填进度" onMouseUp={(e) => void patch({ progress: Number((e.target as HTMLInputElement).value) })}
          onKeyUp={(e) => void patch({ progress: Number((e.target as HTMLInputElement).value) })} /></label>
      )}
      {item.linked_task && <p>关联的平台任务：<Link to={`/tasks/${item.linked_task.id}`}>{item.linked_task.title}</Link>（{item.linked_task.status_name}）</p>}
      <textarea aria-label="备注" defaultValue={item.notes} placeholder="备注" onBlur={(e) => e.target.value !== item.notes && void patch({ notes: e.target.value })} />

      <h4>清单</h4>
      <ul className="list">
        {item.children.map((c) => (
          <li key={c.id}>
            <label><input type="checkbox" checked={c.status === 'done'} aria-label={`完成：${c.title}`}
              onChange={() => void act(() => client.updateWorkbenchItem(c.id, { status: c.status === 'done' ? 'todo' : 'done' }))} /> {c.title}</label>
            {c.notes && <span className="muted"> · {c.notes}</span>}
          </li>
        ))}
      </ul>
      <div className="row">
        <input className="grow" aria-label="新清单项" placeholder="加一项清单" value={newStep} onChange={(e) => setNewStep(e.target.value)} />
        <button className="ghost" onClick={() => newStep.trim() && void act(async () => { await client.addWorkbenchChildren(item.id, [{ title: newStep, note: '' }]); setNewStep(''); })}>加入清单</button>
        <button onClick={() => void act(async () => {
          const res = await client.workbenchBreakdown(item.id);
          setDraft(res.steps);
          if (res.references?.length) setRefs(res.references);
        })}>让助手拆一下</button>
        {item.parent_id === null && methods.length > 0 && (
          <select aria-label="套用我的方法" value="" onChange={(e) => e.target.value && void act(() => client.applyMethod(Number(e.target.value), item.id))}>
            <option value="">套用我的方法…</option>
            {methods.map((m) => <option key={m.id} value={m.id}>{m.name}（{m.steps.length} 步）</option>)}
          </select>
        )}
      </div>
      {refs.length > 0 && (
        <div aria-label="相关笔记">
          <p className="muted">你以前记过的相关内容{draft ? '（助手拆的时候参考了这些）' : ''}：</p>
          <ul className="list">{refs.map((r) => (
            <li key={r.note_id}><Link to={`/notebook?tab=all&note=${r.note_id}`}>{r.title}</Link><span className="muted"> · {r.snippet}</span></li>
          ))}</ul>
        </div>
      )}
      {draft && (
        <div className="card" aria-label="助手拆出的草稿">
          <p className="muted">助手给的草稿，确认后才会加进清单。可以先删掉不需要的。</p>
          <ul className="list">{draft.map((s, n) => (
            <li key={n}>{s.title}{s.note && <span className="muted"> · {s.note}</span>}
              <button className="ghost" onClick={() => setDraft(draft.filter((_, k) => k !== n))} aria-label={`去掉：${s.title}`}>去掉</button></li>
          ))}</ul>
          <div className="row">
            <button disabled={!draft.length} onClick={() => void act(async () => { await client.addWorkbenchChildren(item.id, draft); setDraft(null); })}>确认加入清单</button>
            <button className="ghost" onClick={() => setDraft(null)}>不要了</button>
          </div>
        </div>
      )}

      <h4>进展记录</h4>
      <div className="row">
        <input className="grow" aria-label="写一条进展" placeholder="今天做到哪了？" value={note} onChange={(e) => setNote(e.target.value)} />
        <button onClick={() => note.trim() && void act(async () => { await client.addWorkbenchLog(item.id, note); setNote(''); })}>记一笔</button>
      </div>
      <ul className="list">{logs.map((g) => <li key={g.id}><span className="muted">{formatDateTime(g.created_at)}</span> {g.body}</li>)}</ul>
      <div className="row">
        <Link className="button-link" to={`/publish?title=${encodeURIComponent(item.title)}&description=${encodeURIComponent(item.notes)}`}>找人一起做（转成平台任务）</Link>
        <button className="ghost" onClick={() => window.confirm('删除这个任务和它的清单、进展？') && void act(async () => { await client.deleteWorkbenchItem(item.id); onClose(); })}>删除</button>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

const RUN_STATUS: Record<WbRunStatus, string> = { ok: '成功', failed: '失败', retrying: '失败，等待重试', skipped: '跳过（数据没就绪）', degraded: '降级送达' };
const KIND: Record<string, string> = { digest: '概览（今天要做的、逾期的、平台上等我处理的）', review: '回顾（这周完成了什么）', reminder: '提醒' };
const FREQ: Record<string, string> = { once: '一次', daily: '每天', weekly: '每周', monthly: '每月' };
const WEEK = ['一', '二', '三', '四', '五', '六', '日'];

function Assistant() {
  const { client } = useApp();
  const [mem, setMem] = useState<{ limit: number; items: WbMemory[] }>({ limit: 20, items: [] });
  const [routines, setRoutines] = useState<WbRoutine[]>([]);
  const [runs, setRuns] = useState<Record<number, WbRoutineRun[]>>({});
  const [content, setContent] = useState('');
  // REL-101 新建时默认给一份运行合同：失败重试 2 次（1 分钟、5 分钟后），重试用尽时降级交付（130 号 spec）
  const [form, setForm] = useState<WbRoutineInput>({ name: '每天早上的概览', kind: 'digest', freq: 'daily', time_of_day: '08:30', weekday: 0, monthday: 1, note: '',
    max_retries: 2, degrade: true, timeout_ms: 10000 });
  const [health, setHealth] = useState<Record<number, WbRoutineHealth>>({});
  // REL-110 本月助手成本（131 号 spec）：取不到就不显示
  const [costs, setCosts] = useState<AssistantCosts | null>(null);
  useEffect(() => { Promise.resolve().then(() => client.assistantCosts()).then((c) => setCosts(c && typeof c.total_cents === 'number' ? c : null)).catch(() => setCosts(null)); }, [client]);
  const [error, setError] = useState('');
  const [flash, setFlash] = useState('');

  const load = useCallback(async () => {
    try { setMem(await client.workbenchMemories()); setRoutines(await client.workbenchRoutines()); } catch (e) { setError(apiErrorText(e)); }
  }, [client]);
  useEffect(() => { void load(); }, [load]);
  async function act(fn: () => Promise<unknown>) {
    setError(''); setFlash('');
    try { await fn(); await load(); } catch (e) { setError(apiErrorText(e)); }
  }

  return (
    <>
      <div className="card">
        <h3>助手记得的事（{mem.items.length}/{mem.limit}）</h3>
        <p className="muted">比如「周末不安排工作」「报告要先给结论」。助手拆任务时会参考这些；只有你看得到，可以随时删。</p>
        <ul className="list">{mem.items.map((m) => (
          <li key={m.id}>{m.content} <button className="ghost" aria-label={`忘掉：${m.content}`} onClick={() => void act(() => client.deleteWorkbenchMemory(m.id))}>忘掉</button></li>
        ))}</ul>
        <div className="row">
          <input className="grow" aria-label="让助手记住" placeholder="让助手记住一件事" maxLength={200} value={content} onChange={(e) => setContent(e.target.value)} />
          <button onClick={() => content.trim() && void act(async () => { await client.addWorkbenchMemory(content); setContent(''); })}>记住</button>
        </div>
      </div>

      <div className="card">
        <h3>例行任务</h3>
        {costs && <p className="muted" aria-label="本月助手成本">本月助手成本 {fmtYuan(costs.total_cents)} / 上限 {fmtYuan(costs.cap_cents)}（经验工具 {costs.agent_calls} 次）。要让 AI 帮你把一个目标拆成任务去办，用 <Link to="/missions">AI 编排</Link>。</p>}
        <p className="muted">到点由平台运行，结果发到你的通知里，不需要开着网页。连续失败 3 次会自动暂停并告诉你。时间按北京时间算。</p>
        <ul className="list">{routines.map((r) => (
          <li key={r.id} data-routine={r.id}>
            <strong>{r.name}</strong> · {FREQ[r.freq]}{r.freq === 'weekly' ? `周${WEEK[r.weekday]}` : ''}{r.freq === 'monthly' ? `${r.monthday} 号` : ''}{r.freq !== 'once' ? ` ${r.time_of_day}` : ''} · {KIND[r.kind].split('（')[0]}
            {' · '}{r.enabled ? `下次 ${formatDateTime(r.next_run_at)}` : '已暂停'}
            {r.last_status && <span className={r.last_status === 'failed' ? 'error' : 'muted'}> · 上次{RUN_STATUS[r.last_status]}</span>}
            <span className="muted"> · 失败重试 {r.max_retries} 次{r.degrade ? '，用尽后降级交付' : ''}</span>
            <div className="row">
              <button className="ghost" onClick={() => void act(async () => { const res = await client.runWorkbenchRoutine(r.id); setFlash(res.output); })}>现在运行一次</button>
              <button className="ghost" onClick={() => void act(() => client.updateWorkbenchRoutine(r.id, { enabled: !r.enabled }))}>{r.enabled ? '暂停' : '开启'}</button>
              <button className="ghost" onClick={() => void client.workbenchRoutineRuns(r.id).then((x) => setRuns({ ...runs, [r.id]: x }))}>运行记录</button>
              <button className="ghost" onClick={() => void client.workbenchRoutineHealth(r.id).then((x) => setHealth({ ...health, [r.id]: x }))}>健康度</button>
              <button className="ghost" onClick={() => void act(() => client.deleteWorkbenchRoutine(r.id))}>删除</button>
            </div>
            {health[r.id] && (
              <p className="muted" aria-label={`健康度：${r.name}`}>最近 {health[r.id].runs} 次：成功率 {health[r.id].success_rate === null ? '—' : `${Math.round(health[r.id].success_rate! * 100)}%`}
                {' '}· 降级 {health[r.id].degraded} · 重试 {health[r.id].retries} · 跳过 {health[r.id].skipped}
                {health[r.id].p50_ms !== null ? ` · 耗时中位 ${health[r.id].p50_ms} 毫秒` : ''}
                {health[r.id].error_kinds.length ? ` · 出错：${health[r.id].error_kinds.map((k) => `${k.kind} ${k.count} 次`).join('、')}` : ''}</p>
            )}
            {runs[r.id] && <ul className="list">{runs[r.id].map((x) => <li key={x.id}><span className="muted">{formatDateTime(x.started_at)} {RUN_STATUS[x.status]}{x.attempt > 1 ? `（第 ${x.attempt} 次尝试）` : ''}</span> {x.output}</li>)}
              {!runs[r.id].length && <li className="muted">还没有运行过。</li>}</ul>}
          </li>
        ))}</ul>
        {flash && <p data-testid="wb-run-output">{flash}</p>}
        <div className="form">
          <input aria-label="例行任务名称" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <select aria-label="做什么" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as WbRoutineInput['kind'] })}>
            {Object.entries(KIND).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
          <select aria-label="多久一次" value={form.freq} onChange={(e) => setForm({ ...form, freq: e.target.value as WbRoutineInput['freq'] })}>
            {Object.entries(FREQ).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
          {form.freq === 'weekly' && <select aria-label="周几" value={form.weekday} onChange={(e) => setForm({ ...form, weekday: Number(e.target.value) })}>
            {WEEK.map((w, n) => <option key={n} value={n}>周{w}</option>)}</select>}
          {form.freq === 'monthly' && <input type="number" min={1} max={31} aria-label="几号" value={form.monthday} onChange={(e) => setForm({ ...form, monthday: Number(e.target.value) })} />}
          {form.freq === 'once'
            ? <input type="datetime-local" aria-label="运行时间" onChange={(e) => setForm({ ...form, run_at: e.target.value ? localInputToServerTime(e.target.value) : null })} />
            : <input type="time" aria-label="几点" value={form.time_of_day} onChange={(e) => setForm({ ...form, time_of_day: e.target.value })} />}
          {form.kind === 'reminder' && <input aria-label="提醒内容" placeholder="提醒我什么" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />}
          <select aria-label="失败后重试" value={form.max_retries} onChange={(e) => setForm({ ...form, max_retries: Number(e.target.value) })}>
            {[0, 1, 2, 3].map((n) => <option key={n} value={n}>{n ? `失败后重试 ${n} 次` : '失败不重试'}</option>)}</select>
          <label><input type="checkbox" aria-label="重试用尽时降级交付" checked={!!form.degrade} onChange={(e) => setForm({ ...form, degrade: e.target.checked })} /> 重试用尽时降级交付</label>
          <button onClick={() => void act(() => client.createWorkbenchRoutine(form))}>添加例行任务</button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
    </>
  );
}
