import { apiErrorText, fmtYuan, parseQuoteCard, type Conversation, type Message, type Task } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useApp } from '../store';

export default function Messages() {
  const { client, me } = useApp();
  const [params] = useSearchParams();
  const requestedConversation = Number(params.get('conversation'));
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [active, setActive] = useState<Conversation | null>(null);
  const [msgs, setMsgs] = useState<Message[]>([]);
  const [text, setText] = useState('');
  const [warning, setWarning] = useState<string | null>(null);
  // SCN-172（299 号 spec）只给发送的人看的心理援助热线
  const [support, setSupport] = useState('');
  const [peer, setPeer] = useState('');

  useEffect(() => {
    let alive = true;
    void client.conversations().then(async rows => {
      if (!alive) return;
      setConvs(rows);
      const selected = rows.find(c => c.id === requestedConversation);
      if (selected) { const messages = await client.messages(selected.id); if (alive) { setActive(selected); setMsgs(messages); } }
    }).catch(e => { if (alive) setWarning(apiErrorText(e)); });
    return () => { alive = false; };
  }, [client, requestedConversation]);

  const openConv = useCallback(async (c: Conversation) => {
    setActive(c);
    setMsgs(await client.messages(c.id));
  }, [client]);

  async function send() {
    if (!active || !text.trim()) return;
    const res = await client.sendMessage(active.id, text).catch((e) => {
      setWarning(e.message);
      return null;
    });
    if (res) {
      setWarning(res.warning);
      setSupport(res.support ?? '');
      setText('');
      setMsgs(await client.messages(active.id));
    }
  }

  return (
    <div className="page" style={{ gridTemplateColumns: '260px 1fr', display: 'grid' }}>
      <div className="card">
        <h3>会话</h3>
        <div className="list" style={{ marginTop: 8 }}>
          {convs.length === 0 && <p className="muted">暂无会话</p>}
          {convs.map((c) => (
            <a key={c.id} onClick={() => void openConv(c)} style={{ cursor: 'pointer' }}>
              {c.kind === 'task' ? '📋' : '💬'} {'title' in c && c.title ? String(c.title) : (c.kind === 'task' ? `任务会话 #${c.task_id}` : `私聊 #${c.id}`)}
            </a>
          ))}
        </div>
        {/* IM-020 成交前也要说得上话。任务会话要等**合约托管成功**才自动建，
            而「你几点能到」「要不要带工具」全发生在托管之前——
            `openDirect` 建好了，此前**没有任何一个端调用过它**。 */}
        <div className="row" style={{ marginTop: 12 }}>
          <input style={{ width: 110 }} placeholder="对方用户 ID" value={peer}
                 onChange={(e) => setPeer(e.target.value)} />
          <button disabled={!peer} onClick={async () => {
            setWarning(null);
            try {
              const conv = await client.openDirect(Number(peer));
              setPeer('');
              setConvs(await client.conversations());
              await openConv(conv);
            } catch (err) {
              setWarning(apiErrorText(err));   // 拉黑等理由原样显示
            }
          }}>发起会话</button>
        </div>
      </div>
      <div className="card">
        {!active && <p className="muted">选择一个会话开始聊天</p>}
        {active && (
          <>
            <div className="chat">
              {msgs.map((m) => (
                <div key={m.id} className={`bubble ${m.sender_id === me?.id ? 'mine' : ''}`}>
                  {m.kind === 'quote' && parseQuoteCard(m.content)
                    ? <QuoteCardView card={parseQuoteCard(m.content)!} mine={m.sender_id === me?.id}
                                     onApply={async (c) => {
                                       setWarning(null);
                                       try { await client.apply(c.task_id, c.note || '按私信里的报价报名', c.price_cents); setWarning('已按这个价报名，等发布方确认'); }
                                       catch (err) { setWarning(apiErrorText(err)); }
                                     }} />
                    : m.content}
                  {m.risk_flagged && <span title="疑似站外引导"> ⚠️</span>}
                  {/* IM-004 服务端给了 2 分钟撤回窗口，此前**没有任何端能点**。
                      过期与否由服务端判并给理由，客户端不重算那 2 分钟。 */}
                  {m.sender_id === me?.id && !m.recalled && (
                    <button className="ghost" style={{ padding: '0 6px', marginLeft: 6 }}
                            onClick={async () => {
                              setWarning(null);
                              try {
                                await client.recallMessage(m.id);
                                if (active) setMsgs(await client.messages(active.id));
                              } catch (err) {
                                setWarning(apiErrorText(err));
                              }
                            }}>撤回</button>
                  )}
                </div>
              ))}
            </div>
            {warning && <p className="error">⚠️ {warning}</p>}
            {support && <p role="status" className="badge warn" data-testid="crisis-support">{support}</p>}
            <div className="row" style={{ marginTop: 8 }}>
              <input className="grow" value={text} onChange={(e) => setText(e.target.value)}
                     onKeyDown={(e) => e.key === 'Enter' && void send()} placeholder="输入消息…" />
              <button onClick={() => void send()}>发送</button>
            </div>
            <QuoteComposer convTaskId={active.task_id} onSend={async (taskId, cents, note) => {
              setWarning(null);
              try { await client.sendQuoteCard(active.id, taskId, cents, note); setMsgs(await client.messages(active.id)); }
              catch (err) { setWarning(apiErrorText(err)); }
            }} />
          </>
        )}
      </div>
    </div>
  );
}


/** IM-009 报价卡。发布方报自己的单（「我出这个价请你做」）→ 对方可以按这个价报名；
 *  执行方对发布方的单报价 → 发布方去任务页的报名列表里选 TA。 */
function QuoteCardView({ card, mine, onApply }: {
  card: NonNullable<ReturnType<typeof parseQuoteCard>>; mine: boolean; onApply: (c: NonNullable<ReturnType<typeof parseQuoteCard>>) => void;
}) {
  return (
    <div className="quote-card" data-testid="quote-card">
      <strong>报价 {fmtYuan(card.price_cents)}</strong>
      <div><Link to={`/tasks/${card.task_id}`}>{card.title ? `《${card.title}》` : `任务 #${card.task_id}`}</Link></div>
      {card.note && <div className="muted">{card.note}</div>}
      {!mine && card.from_creator && <button onClick={() => onApply(card)}>按这个价报名</button>}
      {!mine && card.from_creator === false && <span className="muted">对方按这个价想接你的单：去任务页的报名列表里选 TA</span>}
    </div>
  );
}

function QuoteComposer({ convTaskId, onSend }: { convTaskId: number | null; onSend: (taskId: number, cents: number, note: string) => void }) {
  const { client } = useApp();
  const [open, setOpen] = useState(false);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskId, setTaskId] = useState('');
  const [price, setPrice] = useState('');
  const [note, setNote] = useState('');
  useEffect(() => {
    if (!open) return;
    void client.myTasks({ role: 'posted', status: 'published' }).then(setTasks).catch(() => setTasks([]));
  }, [client, open]);
  if (!open) return <button className="ghost" onClick={() => setOpen(true)}>发报价</button>;
  const chosen = convTaskId ?? (taskId ? Number(taskId) : null);
  return (
    <div className="row" aria-label="发报价" style={{ marginTop: 8 }}>
      {convTaskId === null && (
        <select aria-label="报哪一单" value={taskId} onChange={(e) => setTaskId(e.target.value)}>
          <option value="">选我发布的招募中任务</option>
          {tasks.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
        </select>
      )}
      <input type="number" min={1} aria-label="报价（元）" placeholder="报价（元）" value={price} onChange={(e) => setPrice(e.target.value)} style={{ width: 120 }} />
      <input className="grow" aria-label="说明" placeholder="说明（含哪些、多久完成）" maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} />
      <button disabled={!chosen || !(parseFloat(price) > 0)}
              onClick={() => { onSend(chosen!, Math.round(parseFloat(price) * 100), note); setOpen(false); setPrice(''); setNote(''); }}>发出报价卡</button>
      <button className="ghost" onClick={() => setOpen(false)}>取消</button>
    </div>
  );
}
