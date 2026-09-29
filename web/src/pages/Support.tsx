import { apiErrorText, formatDateTime } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from '../store';

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
function MyTickets() {
  const { client } = useApp();
  const [rows, setRows] = useState<Array<{
    id: number; subject: string; body: string; status: string; reply: string; created_at: string;
  }>>([]);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setRows(await client.myTickets().catch(() => []));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function create() {
    setError('');
    try {
      await client.createTicket(subject, body);
      setSubject(''); setBody('');
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
        {error && <p className="error">{error}</p>}
        <button disabled={subject.trim().length < 2} onClick={() => void create()}>提交工单</button>
      </div>
      <div className="list" style={{ marginTop: 12 }}>
        {rows.length === 0 && <p className="muted">还没有工单。</p>}
        {rows.map((t) => (
          <div className="task-item" key={t.id} data-testid={`ticket-${t.id}`}>
            <div>
              <strong>{t.subject}</strong> <span className="badge">{t.status}</span>
              <p className="muted">{t.body} · {formatDateTime(t.created_at)}</p>
              {/* 运营的回复原文——回复只发一条通知的话，
                  用户回到平台上就再也找不到它 */}
              {t.reply && <p data-testid={`ticket-reply-${t.id}`}>客服回复：{t.reply}</p>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
