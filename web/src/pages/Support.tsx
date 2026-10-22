import { ticketReplyNotice, apiErrorText, formatDateTime, type MyTicket, type TicketCategory, type UrgentHint } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from '../store';
import PhotoPicker from '../PhotoPicker';

interface QA { q: string; a: string; human: boolean; ctx: string | null }

export default function Support() {
  const { client } = useApp();
  const [history, setHistory] = useState<QA[]>([]);
  const [q, setQ] = useState('');

  async function ask() {
    if (!q.trim()) return;
    const res = await client.askSupport(q);
    setHistory((h) => [...h, {
      q,
      a: res.answer,
      human: res.escalate_to_human,
      ctx: res.account_context ? `（你当前可用余额 ¥${(res.account_context.available_cents / 100).toFixed(2)}）` : null,
    }]);
    setQ('');
  }

  return (
    <div className="page">
      <div className="card">
        <h3>智能客服</h3>
        <p className="muted">可以问：平台如何收费 / 资金托管安全吗 / 验收超时怎么办 / 如何发起纠纷 / 如何提现</p>
        <div className="chat" style={{ marginTop: 8 }}>
          {history.map((item, i) => (
            <div key={i} style={{ display: 'contents' }}>
              <div className="bubble mine">{item.q}</div>
              <div className="bubble">
                {item.a}{item.ctx && <em className="muted"> {item.ctx}</em>}
                {item.human && <p className="muted">已生成人工客服工单</p>}
              </div>
            </div>
          ))}
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <input className="grow" value={q} onChange={(e) => setQ(e.target.value)}
                 onKeyDown={(e) => e.key === 'Enter' && void ask()} placeholder="描述你的问题…" />
          <button onClick={() => void ask()}>发送</button>
        </div>
      </div>
      <MyTickets />
    </div>
  );
}

/** CS-032 工单自助（77 号 spec）。
 *
 * 此前工单**只有 FAQ 机器人升级时会自动生成**：用户不能主动开单，
 * 也看不到自己的工单与回复。V101 给运营补了工单队列，运营认真回了，
 * 而提问的人只收到一条通知，回到平台上无处可看。
 */
/** ESCA-057（227 号 spec）工单里的截图：点开看原图 */
export function TicketImages({ urls, label }: { urls?: string[]; label: string }) {
  if (!urls?.length) return null;
  return (
    <span className="row" style={{ gap: 6 }} data-testid={label}>
      {urls.map((u, i) => (
        <a key={u} href={u} target="_blank" rel="noreferrer" aria-label={`截图 ${i + 1}`}>
          <img src={u} alt={`截图 ${i + 1}`} style={{ width: 56, height: 56, objectFit: 'cover', borderRadius: 6 }} />
        </a>
      ))}
    </span>
  );
}

/** ESCA-057 一条消息最多附几张（与服务端 MAX_TICKET_IMAGES 一致） */
const MAX_TICKET_IMAGES = 4;

function MyTickets() {
  const { client } = useApp();
  const [rows, setRows] = useState<MyTicket[]>([]);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [replied, setReplied] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  // ESCA-052（172 号 spec）资金、账号类加急，时限更短
  const [category, setCategory] = useState<TicketCategory>('general');
  const [error, setError] = useState('');
  // ESCA-057（227 号 spec）截图：提单一组、每张工单的补充各一组
  const [images, setImages] = useState<string[]>([]);
  // ESCA-060（229 号 spec）选加急类别时，若最近自选加急多数被改回一般，提示一句（不拦）
  const [urgentHint, setUrgentHint] = useState<UrgentHint | null>(null);
  const [created, setCreated] = useState('');
  useEffect(() => { client.myUrgentHint().then(setUrgentHint).catch(() => setUrgentHint(null)); }, [client]);
  const [draftImages, setDraftImages] = useState<Record<number, string[]>>({});

  const load = useCallback(async () => {
    setRows(await client.myTickets().catch(() => []));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function create() {
    setError('');
    try {
      const r = await client.createTicket(subject, body, category === 'general' ? undefined : category, images);
      setSubject(''); setBody(''); setCategory('general'); setImages([]);
      setCreated(r.priority_note ? `已提交（按加急处理）。${r.priority_note}` : '');
      await load();
    } catch (err) { setError(apiErrorText(err)); }
  }

  return (
    <div className="card">
      <h3>我的工单（{rows.length}）</h3>
      <div className="form" style={{ marginTop: 8 }}>
        <input placeholder="问题一句话概括" value={subject}
               onChange={(e) => setSubject(e.target.value)} />
        <textarea placeholder="详细描述（越具体越快解决）" value={body}
                  onChange={(e) => setBody(e.target.value)} />
        <label>什么类的问题
          <select aria-label="工单类别" value={category} onChange={(e) => setCategory(e.target.value as TicketCategory)}>
            <option value="general">一般</option>
            <option value="funds">资金（提现、退款、到账）· 加急</option>
            <option value="account">账号（登录、安全）· 加急</option>
          </select>
        </label>
        {category !== 'general' && urgentHint?.message && <p className="warn" data-testid="urgent-hint">{urgentHint.message}</p>}
        <span className="muted">截图（最多 {MAX_TICKET_IMAGES} 张，截之前请遮住卡号、证件号）</span>
        <PhotoPicker urls={images} onChange={setImages} max={MAX_TICKET_IMAGES} />
        {error && <p className="error">{error}</p>}
        <button disabled={subject.trim().length < 2} onClick={() => void create()}>提交工单</button>
      </div>
      {replied && <p role="status">{replied}</p>}
      {created && <p className="muted" data-testid="ticket-created-note">{created}</p>}
      <div className="list" style={{ marginTop: 12 }}>
        {rows.length === 0 && <p className="muted">还没有工单。</p>}
        {rows.map((t) => (
          <div className="task-item" key={t.id} data-testid={`ticket-${t.id}`}>
            <div>
              <strong>{t.subject}</strong> <span className="badge">{t.status}</span>
              {t.priority === 'urgent' && <span className="badge warn" data-testid={`ticket-urgent-${t.id}`}> 加急</span>}
              <p className="muted">{t.body} · {formatDateTime(t.created_at)}</p>
              <TicketImages urls={t.images} label={`ticket-images-${t.id}`} />
              {/* 运营的回复原文——回复只发一条通知的话，
                  用户回到平台上就再也找不到它 */}
              {t.reply && <p data-testid={`ticket-reply-${t.id}`}>客服回复：{t.reply}</p>}
              {/* ESCA-053（157 号 spec）往来记录：多于一条时把之前的也列出来 */}
              {((t.replies?.length ?? 0) > 1 || (t.replies ?? []).some((x) => !x.is_staff)) && (
                <ol className="muted" data-testid={`ticket-replies-${t.id}`}>
                  {t.replies.map((x, i) => <li key={i}>{x.is_staff ? '客服' : '我'}（{formatDateTime(x.created_at)}）：{x.body}
                    <TicketImages urls={x.images} label={`ticket-reply-images-${t.id}-${i}`} /></li>)}
                </ol>
              )}
              {/* ESCA-051（150 号 spec）：等的人要知道有没有人在管、是不是已经升级 */}
              {t.status === 'open' && (
                <p className="muted" data-testid={`ticket-progress-${t.id}`}>
                  {t.claimed ? '已有客服接手' : '排队等待客服接手'}{t.first_responded ? ' · 客服已回复' : ''} · 已等 {t.waited_hours} 小时（承诺 {t.sla_hours} 小时内处理）
                  {t.escalation_level >= 2 ? ' · 已升级给客服主管跟进' : t.escalation_level === 1 ? ' · 已超时，已催办' : ''}
                </p>
              )}
              {/* ESCA-056（166 号 spec）补充材料不用再开一张；已结的 7 天内补充会重新打开 */}
              {(t.status === 'open' || t.status === 'resolved') && (
                <div className="row">
                  <input aria-label={`补充工单 ${t.id}`} className="grow" placeholder={t.status === 'resolved' ? '没解决？补充说明会重新打开这张工单' : '补充说明或材料'}
                    value={drafts[t.id] ?? ''} onChange={(e) => setDrafts({ ...drafts, [t.id]: e.target.value })} />
                  <button className="ghost" disabled={!(drafts[t.id] ?? '').trim()} onClick={() => void (async () => {
                    setError('');
                    try {
                      const r = await client.replyMyTicket(t.id, (drafts[t.id] ?? '').trim(), draftImages[t.id]);
                      setDrafts({ ...drafts, [t.id]: '' });
                      setDraftImages({ ...draftImages, [t.id]: [] });
                      setRows(rows.map((x) => (x.id === r.id ? r : x)));
                      setReplied(ticketReplyNotice(r));
                    } catch (e) { setError(apiErrorText(e)); }
                  })()}>补充</button>
                  <PhotoPicker urls={draftImages[t.id] ?? []} onChange={(u) => setDraftImages({ ...draftImages, [t.id]: u })} max={MAX_TICKET_IMAGES} />
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
