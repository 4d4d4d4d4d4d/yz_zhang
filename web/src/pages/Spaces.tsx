import { apiErrorText, type PersonalSpace, type OwnSpace, type SpaceItem, type SpaceSummary } from '@platform/core';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useApp } from '../store';
import { Reveal } from '../Motion';

const LABELS: Record<SpaceItem['kind'], string> = { work: '作品', article: '文章', video: '视频', shop: '小店', live: '直播', service: '服务' };

function WindowArt({ theme = 'clay', small = false }: { theme?: string; small?: boolean }) {
  return <div className={`window-art ${theme} ${small ? 'small' : ''}`} aria-hidden="true"><div className="art-orbit" /><div className="art-slab" /><div className="art-sphere" /><div className="art-frame" /><span className="art-caption">A SPACE OF YOUR OWN</span></div>;
}

export function Discover() {
  const { client, hasToken } = useApp();
  const [people, setPeople] = useState<SpaceSummary[]>([]);
  const [q, setQ] = useState('');
  const [activeQuery, setActiveQuery] = useState('');
  const [cursor, setCursor] = useState<number | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const request = useRef(0);
  async function load(query: string, after = 0) {
    const seq = ++request.current;
    setBusy(true); setError('');
    try {
      const result = await client.discoverSpaces(query, after);
      if (seq !== request.current) return;
      if (!result || !Array.isArray(result.items)) throw new Error('Invalid space response');
      setPeople(old => after ? [...old, ...result.items] : result.items); setCursor(result.next_cursor); setActiveQuery(query);
    } catch (e) { if (seq === request.current) setError(apiErrorText(e)); }
    finally { if (seq === request.current) setBusy(false); }
  }
  useEffect(() => { void load(''); const invalidate = () => { request.current++; }; return invalidate; /* invalidate request sequence, not a DOM ref */
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client]);
  return <main className="page discovery-page">
    <section className="discovery-hero">
      <div className="discovery-copy"><span className="overline">OPC · OPEN POSSIBILITIES</span><h1>世界很大。<br /><span>从彼此开始。</span></h1><p>在这里，安放你的热爱、作品与可能。</p><Link className="solid-link" to={hasToken ? '/space/edit' : '/login?next=/space/edit'}>打开我的空间 <span>↗</span></Link><a className="quiet-link" href="#people">先认识一些人 ↓</a></div>
      <div className="hero-window"><WindowArt /><div className="window-note"><span>每一种独特，都有自己的窗口。</span><span>01 — ∞</span></div></div>
    </section>
    <section id="people" className="people-section"><div className="discovery-heading"><div><span className="overline">MEET THE POSSIBILITIES</span><h2>遇见彼此</h2></div><form className="people-search" onSubmit={e => { e.preventDefault(); void load(q); }}><input aria-label="搜索人与能力" placeholder="名字、兴趣，或一种可能…" value={q} onChange={e => setQ(e.target.value)} /><button className="ghost" type="submit" aria-label="搜索空间">↗</button></form></div>
    {error && <p role="alert" className="error">{error} <button className="ghost" onClick={() => void load(activeQuery)}>重试</button></p>}
    {busy && <p className="muted" role="status">正在打开这些窗口…</p>}
    <div className="people-grid">{people.map((p, i) => <Reveal key={p.user_id} delayMs={Math.min(i, 5) * 40}><Link to={`/people/${p.user_id}`} className={`person-window ${p.theme}`}><WindowArt theme={p.theme} small /><div className="person-window-body"><span className="person-initial">{p.nickname.slice(0, 1) || '·'}</span><div><h3>{p.nickname}</h3><p>{p.headline}</p></div><span className="person-arrow">↗</span></div><div className="person-window-footer"><span>{p.kind === 'person' ? '独立个体' : p.kind === 'agent' ? '智能体' : '组织空间'}</span><span>{p.items_count} 个展示</span></div></Link></Reveal>)}</div>
    {!busy && !error && people.length === 0 && <div className="space-empty"><span className="empty-window" aria-hidden="true">↗</span><h3>{activeQuery ? '还没有找到这个空间' : '第一扇窗口，等你打开'}</h3><p>{activeQuery ? '试试另一个名字或关键词。' : '放上一件作品、一篇文章，或你正在做的事。'}</p><Link className="quiet-link" to={hasToken ? '/space/edit' : '/login?next=/space/edit'}>布置我的空间 →</Link></div>}
    {cursor !== null && !error && <button disabled={busy} className="ghost more-spaces" onClick={() => void load(activeQuery, cursor)}>再认识一些人 ↓</button>}
    </section><section className="invitation-strip"><span className="overline">SOMETHING STARTS HERE</span><h2>一个想法，<br />可以从一场对话开始。</h2><Link to="/cooperate" className="quiet-link">看看正在发生的合作 ↗</Link></section>
  </main>;
}

export function PublicSpace() {
  const { id } = useParams(); const { client, me, hasToken } = useApp(); const nav = useNavigate();
  const [space, setSpace] = useState<PersonalSpace | null>(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  useEffect(() => { let live = true; setSpace(null); setError(''); void client.personalSpace(Number(id)).then(s => { if (live) setSpace(s); }).catch(e => { if (live) setError(apiErrorText(e)); }); return () => { live = false; }; }, [client, id]);
  async function contact() {
    if (!hasToken) { nav(`/login?next=${encodeURIComponent(`/people/${id}`)}`); return; }
    setBusy(true); setError('');
    try { const c = await client.openDirect(Number(id)); nav(`/messages?conversation=${c.id}`); }
    catch (e) { setError(apiErrorText(e)); } finally { setBusy(false); }
  }
  return <main className={`page personal-space ${space?.theme || 'clay'}`}><Link className="quiet-link" to="/">← 发现</Link>{error && <p role="alert" className="error">{error}</p>}{!space && !error && <p role="status">正在打开空间…</p>}{space && <>
    <header className="personal-intro"><div><span className="overline">{space.kind === 'person' ? 'INDEPENDENT / 独立个体' : space.kind === 'agent' ? 'AGENT / 智能体' : 'ORGANIZATION / 组织'}</span><h1>{space.nickname}</h1><p className="personal-headline">{space.headline}</p><div className="personal-actions">{me?.id === space.user_id ? <Link className="solid-link" to="/space/edit">编辑我的空间 ↗</Link> : <button disabled={busy} onClick={() => void contact()}>聊聊一个想法 ↗</button>}<span className="muted">{space.accepting_orders ? '愿意认识新的合作伙伴' : '先认识，慢慢聊'}</span></div></div><WindowArt theme={space.theme} /></header>
    {space.introduction && <section className="personal-about"><span className="overline">ABOUT / 关于我</span><p>{space.introduction}</p></section>}
    <div className="discovery-heading"><h2>我的世界</h2><span className="muted">作品、日常与正在发生的事</span></div><div className="portfolio-grid">{space.items.map((item, index) => <Reveal key={index} delayMs={Math.min(index, 5) * 40}><article className={`portfolio-piece piece-${index % 3}`}><span className="overline">{LABELS[item.kind]} / {String(index + 1).padStart(2, '0')}</span><div className="piece-symbol" aria-hidden="true">{['↗', '◎', '✳'][index % 3]}</div><h3>{item.title}</h3><p>{item.summary}</p>{item.url && <a href={item.url} target="_blank" rel="noopener noreferrer" className="quiet-link">{item.kind === 'shop' ? '去逛逛' : item.kind === 'live' ? '前往直播平台' : '打开内容'} ↗ <small>外部平台</small></a>}</article></Reveal>)}</div>{!space.items.length && <p className="space-empty">这个空间正在慢慢生长。</p>}
  </>}</main>;
}

export function EditSpace() {
  const { client } = useApp(); const [space, setSpace] = useState<OwnSpace | null>(null); const [error, setError] = useState(''); const [saved, setSaved] = useState(''); const [busy, setBusy] = useState(false); const [dirty, setDirty] = useState(false);
  useEffect(() => { let alive = true; void client.ownSpace().then(s => { if (alive) setSpace(s); }).catch(e => { if (alive) setError(apiErrorText(e)); }); return () => { alive = false; }; }, [client]);
  useEffect(() => { function warn(e: BeforeUnloadEvent) { if (dirty) { e.preventDefault(); e.returnValue = ''; } } window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn); }, [dirty]);
  function change(patch: Partial<OwnSpace>) { setSpace(s => s ? { ...s, ...patch } : s); setDirty(true); setSaved(''); }
  function itemChange(i: number, patch: Partial<SpaceItem>) { if (space) change({ items: space.items.map((item, n) => n === i ? { ...item, ...patch } : item) }); }
  async function save(e: FormEvent) { e.preventDefault(); if (!space) return; setBusy(true); setError(''); setSaved(''); try { const result = await client.saveSpace({ revision: space.revision, published: space.published, headline: space.headline, introduction: space.introduction, theme: space.theme, items: space.items }); setSpace(result); setDirty(false); setSaved(result.published ? '空间已公开，可以分享给朋友了。' : '已保存，仅你可见。'); } catch (e) { setError(apiErrorText(e)); } finally { setBusy(false); } }
  return <main className="page space-editor"><div className="discovery-heading"><div><span className="overline">MAKE YOURSELF AT HOME</span><h1>我的空间</h1></div><Link className="quiet-link" to="/profile">账户与隐私 ↗</Link></div>{error && <p role="alert" className="error">{error}</p>}{!space && !error && <p>正在加载…</p>}{space && <form onSubmit={e => void save(e)}><fieldset disabled={busy}><div className="editor-layout"><div className="editor-fields"><label>一句话，让人认识你<input required={space.published} maxLength={120} value={space.headline} placeholder="做机器人，也喜欢周末在山里走走。" onChange={e => change({ headline: e.target.value })} /></label><label>关于我<textarea rows={5} maxLength={1600} value={space.introduction} placeholder="你在做什么，又期待遇见谁？" onChange={e => change({ introduction: e.target.value })} /></label><label>空间色调<select value={space.theme} onChange={e => change({ theme: e.target.value as OwnSpace['theme'] })}><option value="clay">陶土 / 温暖</option><option value="moss">苔绿 / 自然</option><option value="ink">墨蓝 / 安静</option></select></label></div><div className="editor-preview"><WindowArt theme={space.theme} /><h2>{space.nickname}</h2><p>{space.headline || '这里，将是你的窗口。'}</p><span className="overline">空间预览</span></div></div>
    <div className="discovery-heading"><h2>放进你的世界</h2><button className="ghost" type="button" disabled={space.items.length >= 24} onClick={() => change({ items: [...space.items, { title: '', summary: '', kind: 'work', url: '' }] })}>＋ 添加内容</button></div>
    {space.items.map((item, i) => <div className="editor-item" key={i}><div className="row"><span className="overline">{String(i + 1).padStart(2, '0')}</span><select aria-label={`内容 ${i + 1} 类型`} value={item.kind} onChange={e => itemChange(i, { kind: e.target.value as SpaceItem['kind'] })}>{Object.entries(LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><button className="ghost" type="button" disabled={i === 0} onClick={() => { const next = [...space.items]; [next[i - 1], next[i]] = [next[i], next[i - 1]]; change({ items: next }); }}>上移</button><button className="ghost" type="button" onClick={() => change({ items: space.items.filter((_, n) => i !== n) })}>移除</button></div><label>标题<input required maxLength={100} value={item.title} onChange={e => itemChange(i, { title: e.target.value })} /></label><label>介绍<textarea maxLength={500} rows={2} value={item.summary} onChange={e => itemChange(i, { summary: e.target.value })} /></label><label>原平台链接（可选）<input type="url" pattern="https://.*" maxLength={1500} placeholder="https://" value={item.url} onChange={e => itemChange(i, { url: e.target.value })} /></label></div>)}
    {!space.items.length && <p className="muted">从一件代表作、一篇文章，或一个小店开始。</p>}<div className="editor-save"><label className="publish-check"><input type="checkbox" checked={space.published} onChange={e => change({ published: e.target.checked })} />公开空间，让别人发现我</label><p className="muted">公开后，任何人都能通过链接浏览以上内容。关闭并保存即可收起；账户隐私限制仍然生效。</p>{!space.profile_public && <p className="error">当前账户设置为不公开；请前往账户与隐私调整后再发布。</p>}<div className="row"><button type="submit" disabled={busy}>{busy ? '正在保存…' : '保存空间'}</button>{space.published && !dirty && <Link to={`/people/${space.user_id}`} className="quiet-link">看看我的门面 ↗</Link>}</div>{saved && <p role="status">{saved}</p>}</div></fieldset></form>}</main>;
}
