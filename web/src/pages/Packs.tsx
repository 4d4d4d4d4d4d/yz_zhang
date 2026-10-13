import {
  apiErrorText, formatDateTime,
  type PackAnswer, type PackAssistant, type ScenarioPackCard,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useApp } from '../store';

/** PACK-100 服务包（123 号 spec）：平台把服务某类人某个痛点的助手专家、方法、知识、例行任务打成一包。
 *
 * 启用＝复制进我的知识库与工作台（之后就是我自己的，可改可删）；助手专家只用白名单工具、每句带出处，
 * 碰钱、签署、申报的事只给草稿，必须本人确认。
 */
const SEGMENT: Record<string, string> = {
  opc: '一人公司', gig: '接单者', creator: '创作者', studio: '工作室', buyer: '发单方', general: '所有人',
};

export default function Packs() {
  const { client } = useApp();
  const [params, setParams] = useSearchParams();
  const openKey = params.get('pack');
  const [cards, setCards] = useState<ScenarioPackCard[]>([]);
  const [error, setError] = useState('');
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  const [single, setSingle] = useState<ScenarioPackCard | null>(null);
  useEffect(() => { client.scenarioPacks().then(setCards).catch((e) => setError(apiErrorText(e))); }, [client, version]);
  // 分享出去的链接（?pack=key）：列表里没有时单独取一次（比如列表还没加载完、或只想看这一个）
  useEffect(() => {
    if (openKey) client.scenarioPack(openKey).then(setSingle).catch((e) => setError(apiErrorText(e)));
  }, [client, openKey, version]);
  const open = cards.find((c) => c.key === openKey) ?? (single?.key === openKey ? single : undefined);

  return (
    <div className="page workbench">
      <div className="page-heading">
        <h2>服务包</h2>
        <p className="muted">每个服务包解决一类人的一件麻烦事：助手专家 + 做法清单 + 带出处的知识 + 定时提醒。启用后复制进你的知识库和工作台。</p>
      </div>
      {error && <p className="error">{error}</p>}
      {open ? <PackDetail card={open} onBack={() => setParams({})} onChanged={refresh} /> : (
        <>
          {!cards.length && <p className="muted">还没有上线的服务包。</p>}
          {cards.map((c) => (
            <div className="card" key={c.key}>
              <div className="row">
                <h3 className="grow"><button className="text-link" onClick={() => setParams({ pack: c.key })}>{c.title}</button></h3>
                <span className="badge">{SEGMENT[c.segment] ?? c.segment}</span>
                {c.enabled && <span className="badge ok">已启用{c.upgrade_available ? ' · 有新版本' : ''}</span>}
              </div>
              <p>{c.summary}</p>
              <ul>{c.pains.map((p) => <li key={p}>{p}</li>)}</ul>
              <p className="muted">
                {c.assets.assistants.length} 位助手专家 · {c.assets.methods.length} 份做法清单 · {c.assets.knowledge.length} 条知识
                {c.assets.routines.length ? ` · ${c.assets.routines.length} 个定时提醒` : ''} · {c.active_users} 人在用
              </p>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

function PackDetail({ card, onBack, onChanged }: { card: ScenarioPackCard; onBack: () => void; onChanged: () => void }) {
  const { client } = useApp();
  const [withRoutines, setWithRoutines] = useState(true);
  const [removeCopies, setRemoveCopies] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [voted, setVoted] = useState(false);

  async function enable() {
    setError(''); setNotice('');
    try {
      const r = await client.enablePack(card.key, withRoutines);
      setNotice(`已启用：装进了 ${r.installed.methods} 份做法、${r.installed.notes} 条知识、${r.installed.routines} 个定时提醒。它们现在是你自己的，可以改。`);
      onChanged();
    } catch (e) { setError(apiErrorText(e)); }
  }
  async function disable() {
    setError(''); setNotice('');
    try {
      const r = await client.disablePack(card.key, removeCopies);
      setNotice(removeCopies ? `已停用：删掉 ${r.removed} 项没改过的副本，保留 ${r.kept_modified} 项你改过的。` : '已停用：定时提醒已关掉，装进来的东西都还在。');
      onChanged();
    } catch (e) { setError(apiErrorText(e)); }
  }
  async function vote(helpful: boolean) {
    try { await client.packFeedback(card.key, helpful); setVoted(true); } catch (e) { setError(apiErrorText(e)); }
  }

  return (
    <div>
      <button className="ghost" onClick={onBack}>← 全部服务包</button>
      <div className="card">
        <div className="row"><h3 className="grow">{card.title}</h3><span className="muted">第 {card.version} 版 · {card.published_at ? formatDateTime(card.published_at) : ''}</span></div>
        <p>{card.summary}</p>
        {!card.enabled || card.upgrade_available ? (
          <div className="row">
            {card.assets.routines.length > 0 && (
              <label><input type="checkbox" checked={withRoutines} onChange={() => setWithRoutines(!withRoutines)} /> 同时打开定时提醒</label>
            )}
            <button onClick={() => void enable()}>{card.upgrade_available ? `升级到第 ${card.version} 版（只补新增的）` : '启用'}</button>
          </div>
        ) : null}
        {card.enabled && (
          <div className="row">
            <label><input type="checkbox" checked={removeCopies} onChange={() => setRemoveCopies(!removeCopies)} /> 同时删掉没改过的副本</label>
            <button className="ghost" onClick={() => void disable()}>停用</button>
          </div>
        )}
        {notice && <p role="status">{notice}</p>}
        {error && <p className="error">{error}</p>}
      </div>

      {card.assets.assistants.map((a) => <AssistantBox key={a.key} packKey={card.key} a={a} />)}

      <div className="card">
        <h4>做法清单</h4>
        <ul>{card.assets.methods.map((m) => <li key={m.key}>{m.name}（{m.steps} 步）</li>)}</ul>
        <p className="muted">启用后在「知识库 → 我的方法」里，也能在工作台任务上一键套用。</p>
        <h4>知识</h4>
        <ul>{card.assets.knowledge.map((k) => (
          <li key={k.key}>{k.title} <span className="muted">· 出处：{k.source}{k.valid_until ? ` · 有效期至 ${k.valid_until}` : ''}</span></li>
        ))}</ul>
        {card.assets.task_templates.length > 0 && (<><h4>发单模板</h4>
          <ul>{card.assets.task_templates.map((t) => (
            <li key={t.key}>{t.title}（{t.category}） <Link to={`/publish?${new URLSearchParams({ title: t.title, category: t.category, description: t.description })}`}>用这个模板发单</Link>
              <span className="muted"> · 只是预填，发不发你决定</span></li>
          ))}</ul></>)}
        {card.assets.routines.length > 0 && (<><h4>定时提醒</h4>
          <ul>{card.assets.routines.map((r) => <li key={r.key}>{r.name}（{r.time_of_day}）</li>)}</ul></>)}
      </div>
      <div className="row">
        <span className="muted">这个服务包有用吗？</span>
        {voted ? <span>谢谢，已记下</span> : (<>
          <button className="ghost" onClick={() => void vote(true)}>有用</button>
          <button className="ghost" onClick={() => void vote(false)}>没用</button>
        </>)}
      </div>
    </div>
  );
}

function AssistantBox({ packKey, a }: { packKey: string; a: PackAssistant }) {
  const { client } = useApp();
  const [q, setQ] = useState('');
  const [ans, setAns] = useState<PackAnswer | null>(null);
  const [error, setError] = useState('');
  async function ask() {
    setError('');
    try { setAns(await client.askPackAssistant(packKey, a.key, q)); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <div className="card" aria-label={`助手专家：${a.name}`}>
      <h4>{a.name}</h4>
      <p className="muted">{a.persona}</p>
      <p className="muted">不会做：{a.forbidden.join('；')}</p>
      <p className="muted">必须你本人确认：{a.human_gates.join('；')}</p>
      <div className="row">
        <input className="grow" aria-label={`问${a.name}`} placeholder="说说你的情况或问题" value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && q.trim() && void ask()} />
        <button disabled={!q.trim()} onClick={() => void ask()}>问</button>
      </div>
      {error && <p className="error">{error}</p>}
      {ans && (
        <div aria-label="助手的回答">
          {ans.refused || !ans.citations.length ? <p>{ans.answer}</p> : (
            <ol>{ans.citations.map((c) => (
              <li key={c.n}>
                <strong>{c.title}</strong>：{c.snippet}
                <span className="muted"> （出处：{c.note_id ? <Link to={`/notebook?tab=all&note=${c.note_id}`}>{c.source}</Link> : c.source}
                  {c.valid_until ? `；有效期至 ${c.valid_until}` : ''}）</span>
                {c.expired && <span className="error"> 已过有效期，以官方最新为准</span>}
              </li>
            ))}</ol>
          )}
          {ans.remedy && <p><Link to={`/publish?category=${encodeURIComponent(ans.remedy.category)}`}>{ans.remedy.label}</Link></p>}
          {!ans.refused && <p className="muted">{ans.gate_notice}</p>}
        </div>
      )}
    </div>
  );
}
