import {
  asList,
  apiErrorText, fmtYuan, formatDateTime,
  type NbAnswer, type NbMethod, type NbMethodDraft, type NbNote, type NbNoteBrief, type NbSummary, type NbTodoDraft,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useApp } from '../store';

/** KB-100 个人知识库（122 号 spec）：门户 = 助手 + 知识库。
 *
 * 随手记进收件箱 → 整理（标签）→ 检索 → 让助手引用（带出处）→ 纪要抽待办进工作台 → 把做法蒸馏成「我的方法」。
 * 这里的东西只有自己看得到：不公开、不进全站搜索、不进推荐、不进经验库。
 */
type Tab = 'inbox' | 'all' | 'methods' | 'ask';
const KIND: Record<string, string> = { note: '笔记', link: '链接', minutes: '纪要' };

export default function Notebook() {
  const { client } = useApp();
  const [params, setParams] = useSearchParams();
  const tab = (params.get('tab') as Tab) || 'inbox';
  const openId = Number(params.get('note')) || null;
  const [summary, setSummary] = useState<NbSummary | null>(null);
  const [version, setVersion] = useState(0);
  const [error, setError] = useState('');
  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => { client.notebookSummary().then(setSummary).catch((e) => setError(apiErrorText(e))); }, [client, version]);

  function go(next: Partial<{ tab: Tab; note: number | null }>) {
    const p = new URLSearchParams(params);
    if (next.tab) p.set('tab', next.tab);
    if (next.note !== undefined) { if (next.note) p.set('note', String(next.note)); else p.delete('note'); }
    setParams(p);
  }
  async function exportAll() {
    try {
      const out = await client.exportNotebook();
      const url = URL.createObjectURL(new Blob([out.markdown], { type: 'text/markdown' }));
      const a = document.createElement('a');
      a.href = url; a.download = out.filename; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { setError(apiErrorText(e)); }
  }

  return (
    <div className="page workbench">
      <div className="page-heading">
        <h2>我的知识库</h2>
        <p className="muted">随手记、整理、检索，让助手引用你自己记过的东西。只有你自己看得到。</p>
      </div>
      <div className="row" role="tablist" aria-label="知识库视图">
        {([['inbox', `收件箱${summary ? `（${summary.inbox}）` : ''}`], ['all', '全部'], ['methods', `我的方法${summary ? `（${summary.methods}）` : ''}`], ['ask', '问问我的笔记']] as [Tab, string][]).map(([t, label]) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? '' : 'ghost'} onClick={() => go({ tab: t })}>{label}</button>
        ))}
        <span className="grow" />
        <button className="ghost" onClick={() => void exportAll()}>导出 Markdown</button>
      </div>
      {error && <p className="error">{error}</p>}
      {(tab === 'inbox' || tab === 'all') && <Capture onAdded={refresh} />}
      {(tab === 'inbox' || tab === 'all') && (
        <Notes key={tab} inbox={tab === 'inbox'} tags={asList<{ tag: string }>(summary?.tags).map((t) => t.tag)} version={version}
          open={(id) => go({ note: id })} onDistilled={() => { refresh(); go({ tab: 'methods' }); }} />
      )}
      {tab === 'methods' && <Methods version={version} />}
      {tab === 'ask' && <Ask open={(id) => go({ note: id })} />}
      {openId && <NotePanel id={openId} onClose={() => go({ note: null })} onChanged={refresh} />}
    </div>
  );
}

function Capture({ onAdded }: { onAdded: () => void }) {
  const { client } = useApp();
  const [body, setBody] = useState('');
  const [tags, setTags] = useState('');
  const [error, setError] = useState('');
  async function save() {
    setError('');
    try {
      await client.createNote({ body, tags: tags.split(/[\s,，]+/).filter(Boolean) });
      setBody(''); setTags(''); onAdded();
    } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <div className="card">
      <textarea aria-label="随手记" placeholder="一句话、一段会议纪要，或者粘贴一个链接" value={body} onChange={(e) => setBody(e.target.value)} />
      <div className="row">
        <input className="grow" aria-label="标签" placeholder="标签（空格分开，可不填）" value={tags} onChange={(e) => setTags(e.target.value)} />
        <button disabled={!body.trim()} onClick={() => void save()}>记下</button>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function Notes({ inbox, tags, version, open, onDistilled }: {
  inbox: boolean; tags: string[]; version: number; open: (id: number) => void; onDistilled: () => void;
}) {
  const { client } = useApp();
  const [q, setQ] = useState('');
  const [tag, setTag] = useState('');
  const [rows, setRows] = useState<NbNoteBrief[]>([]);
  const [picked, setPicked] = useState<number[]>([]);
  const [draft, setDraft] = useState<NbMethodDraft | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    client.notebookNotes({ q, tag, status: inbox ? 'inbox' : undefined })
      .then(setRows).catch((e) => setError(apiErrorText(e)));
  }, [client, q, tag, inbox, version]);

  async function distill() {
    setError('');
    try { setDraft(await client.distillMethod(picked)); } catch (e) { setError(apiErrorText(e)); }
  }
  async function saveMethod() {
    if (!draft) return;
    setError('');
    try {
      await client.createMethod({ name: draft.name, steps: draft.steps, source_note_ids: draft.source_note_ids });
      setDraft(null); setPicked([]); onDistilled();
    } catch (e) { setError(apiErrorText(e)); }
  }

  return (
    <div>
      <div className="row">
        <input className="grow" aria-label="搜索笔记" placeholder="搜索标题、正文、标签" value={q} onChange={(e) => setQ(e.target.value)} />
        {picked.length > 0 && <button onClick={() => void distill()}>把选中的 {picked.length} 条蒸馏成方法</button>}
      </div>
      {tags.length > 0 && (
        <div className="row" aria-label="标签筛选">
          {tags.map((t) => <button key={t} className={tag === t ? '' : 'ghost'} onClick={() => setTag(tag === t ? '' : t)}>#{t}</button>)}
        </div>
      )}
      {error && <p className="error">{error}</p>}
      {draft && (
        <div className="card" aria-label="方法草稿">
          {draft.found === 'none'
            ? <p className="muted">这几条笔记里没找到步骤列表（编号或圆点）。可以先在笔记里写成「1. 2. 3.」再蒸馏。</p>
            : <p className="muted">从笔记里收出来的步骤草稿，确认后才会保存。可以先删掉不需要的。</p>}
          <input aria-label="方法名" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          <ol>{draft.steps.map((s, n) => (
            <li key={n}>{s.title}{s.note && <span className="muted"> · {s.note}</span>}
              <button className="ghost" aria-label={`去掉：${s.title}`} onClick={() => setDraft({ ...draft, steps: draft.steps.filter((_, k) => k !== n) })}>去掉</button></li>
          ))}</ol>
          <div className="row">
            <button disabled={!draft.steps.length || !draft.name.trim()} onClick={() => void saveMethod()}>保存为我的方法</button>
            <button className="ghost" onClick={() => setDraft(null)}>不要了</button>
          </div>
        </div>
      )}
      {!rows.length && <p className="muted">{inbox ? '收件箱是空的。' : '还没有笔记。'}</p>}
      <ul className="list">
        {rows.map((n) => (
          <li key={n.id}>
            <label><input type="checkbox" aria-label={`选中：${n.title}`} checked={picked.includes(n.id)}
              onChange={() => setPicked(picked.includes(n.id) ? picked.filter((x) => x !== n.id) : [...picked, n.id])} /></label>{' '}
            <button className="text-link" onClick={() => open(n.id)}>{n.pinned ? '📌 ' : ''}{n.title}</button>
            <span className="muted"> · {KIND[n.kind]}{n.tags.length ? ` · ${n.tags.map((t) => `#${t}`).join(' ')}` : ''} · {formatDateTime(n.updated_at)}</span>
            {n.excerpt && <div className="muted">{n.excerpt}</div>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function NotePanel({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const { client } = useApp();
  const [note, setNote] = useState<NbNote | null>(null);
  const [todos, setTodos] = useState<(NbTodoDraft & { keep: boolean })[] | null>(null);
  const [error, setError] = useState('');
  const [done, setDone] = useState('');

  const load = useCallback(async () => {
    try { setNote(await client.note(id)); } catch (e) { setError(apiErrorText(e)); }
  }, [client, id]);
  useEffect(() => { void load(); }, [load]);

  async function patch(p: Parameters<typeof client.updateNote>[1]) {
    if (!note) return;
    setError('');
    try { setNote(await client.updateNote(note.id, { ...p, revision: note.revision })); onChanged(); } catch (e) { setError(apiErrorText(e)); }
  }
  async function extract() {
    if (!note) return;
    setError(''); setDone('');
    try { setTodos((await client.extractNoteTodos(note.id)).items.map((t) => ({ ...t, keep: true }))); } catch (e) { setError(apiErrorText(e)); }
  }
  async function confirmTodos() {
    if (!note || !todos) return;
    setError('');
    try {
      const made = await client.addNoteTodos(note.id, todos.filter((t) => t.keep).map((t) => ({ title: t.title, due_at: t.due_at })));
      setTodos(null); setDone(`已放进工作台 ${made.length} 项`);
    } catch (e) { setError(apiErrorText(e)); }
  }
  if (!note) return error ? <p className="error">{error}</p> : null;
  return (
    <div className="card" role="dialog" aria-label={`笔记：${note.title}`}>
      <div className="row">
        <input className="grow" aria-label="标题" defaultValue={note.title} key={`t${note.revision}`}
          onBlur={(e) => e.target.value.trim() && e.target.value !== note.title && void patch({ title: e.target.value })} />
        <button className="ghost" onClick={onClose}>关闭</button>
      </div>
      {note.url && <p><a href={note.url} target="_blank" rel="noopener noreferrer nofollow">{note.url}</a></p>}
      <textarea aria-label="正文" defaultValue={note.body} key={`b${note.revision}`} rows={8}
        onBlur={(e) => e.target.value !== note.body && void patch({ body: e.target.value })} />
      <input aria-label="编辑标签" defaultValue={note.tags.join(' ')} key={`g${note.revision}`} placeholder="标签（空格分开）"
        onBlur={(e) => { const tags = e.target.value.split(/[\s,，]+/).filter(Boolean); if (tags.join(' ') !== note.tags.join(' ')) void patch({ tags }); }} />
      <p className="muted">{KIND[note.kind]} · {note.status === 'inbox' ? '收件箱' : note.status === 'filed' ? '已整理' : '已归档'} · 记于 {formatDateTime(note.created_at)}</p>
      <div className="row">
        {note.status === 'inbox' && <button className="ghost" onClick={() => void patch({ status: 'filed' })}>整理完了</button>}
        {note.status !== 'archived'
          ? <button className="ghost" onClick={() => void patch({ status: 'archived' })}>归档</button>
          : <button className="ghost" onClick={() => void patch({ status: 'filed' })}>取消归档</button>}
        <button className="ghost" onClick={() => void patch({ pinned: !note.pinned })}>{note.pinned ? '取消置顶' : '置顶'}</button>
        <button onClick={() => void extract()}>抽出待办</button>
        <button className="danger" onClick={() => { if (window.confirm('删除这条笔记？')) void client.deleteNote(note.id).then(() => { onChanged(); onClose(); }).catch((e) => setError(apiErrorText(e))); }}>删除</button>
      </div>
      {todos && (
        <div className="card" aria-label="抽出的待办草稿">
          {!todos.length ? <p className="muted">没找到待办。纪要里写成「- [ ] 事情」「待办：事情」，或者带「负责 / 跟进 / 之前」的列表项，就能认出来。</p> : (
            <>
              <p className="muted">助手认出的待办，确认后才会放进工作台。</p>
              <ul className="list">{todos.map((t, n) => (
                <li key={n}><label><input type="checkbox" checked={t.keep} aria-label={`保留：${t.title}`}
                  onChange={() => setTodos(todos.map((x, k) => (k === n ? { ...x, keep: !x.keep } : x)))} /> {t.title}</label>
                  {t.due_at && <span className="muted"> · 截止 {formatDateTime(t.due_at)}</span>}</li>
              ))}</ul>
              <button disabled={!todos.some((t) => t.keep)} onClick={() => void confirmTodos()}>放进工作台</button>
            </>
          )}
          <button className="ghost" onClick={() => setTodos(null)}>收起</button>
        </div>
      )}
      {done && <p role="status">{done}</p>}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function methodStats(m: NbMethod): string {
  const rate = m.success_rate === null ? '做完的还少，先不算成功率' : `成功率 ${Math.round(m.success_rate * 100)}%`;
  return `编排用过 ${m.missions_total} 次：做成 ${m.missions_succeeded}、没成 ${m.missions_failed}，花了 ${fmtYuan(m.missions_spent_cents)}；${rate}`;
}

function Methods({ version }: { version: number }) {
  const { client } = useApp();
  const [rows, setRows] = useState<NbMethod[]>([]);
  const [error, setError] = useState('');
  const [v, setV] = useState(0);
  useEffect(() => { client.notebookMethods().then(setRows).catch((e) => setError(apiErrorText(e))); }, [client, version, v]);
  return (
    <div>
      <p className="muted">我的方法：从笔记里蒸馏出来、可以反复套用的步骤。在工作台的任务里点「套用我的方法」，步骤就变成清单。</p>
      {error && <p className="error">{error}</p>}
      {!rows.length && <p className="muted">还没有方法。在笔记列表里勾选几条写着步骤的笔记，点「蒸馏成方法」。</p>}
      {rows.map((m) => (
        <div className="card" key={m.id}>
          <div className="row"><input className="grow" aria-label={`方法名：${m.name}`} defaultValue={m.name}
            onBlur={(e) => e.target.value.trim() && e.target.value !== m.name && void client.updateMethod(m.id, { name: e.target.value }).then(() => setV(v + 1)).catch((err) => setError(apiErrorText(err)))} />
            <span className="muted">用过 {m.uses} 次</span>
            {/* AGT-095（168 号 spec）按它拆过的编排做得怎么样 */}
            {m.missions_total > 0 && <span className="muted" data-testid={`method-stats-${m.id}`}>{methodStats(m)}</span>}
            <button className="danger" onClick={() => void client.deleteMethod(m.id).then(() => setV(v + 1)).catch((e) => setError(apiErrorText(e)))}>删除</button></div>
          <ol>{m.steps.map((s, n) => <li key={n}>{s.title}{s.note && <span className="muted"> · {s.note}</span>}</li>)}</ol>
        </div>
      ))}
    </div>
  );
}

function Ask({ open }: { open: (id: number) => void }) {
  const { client } = useApp();
  const [q, setQ] = useState('');
  const [ans, setAns] = useState<NbAnswer | null>(null);
  const [error, setError] = useState('');
  async function ask() {
    setError('');
    try { setAns(await client.askNotebook(q)); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <div className="card">
      <div className="row">
        <input className="grow" aria-label="问我的笔记" placeholder="比如：给企业开专票要什么？" value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && q.trim() && void ask()} />
        <button disabled={!q.trim()} onClick={() => void ask()}>问</button>
      </div>
      {error && <p className="error">{error}</p>}
      {ans && (
        <div aria-label="回答">
          <p className="muted">只从你自己的笔记里摘录，每条都标了出处；没记过的不编。</p>
          {!ans.citations.length ? <p>{ans.answer}</p> : (
            <ol>{ans.citations.map((c) => (
              <li key={c.n}><button className="text-link" onClick={() => open(c.note_id)}>{c.title}</button>：{c.snippet}</li>
            ))}</ol>
          )}
        </div>
      )}
    </div>
  );
}
