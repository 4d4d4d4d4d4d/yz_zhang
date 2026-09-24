import { apiErrorText, type Conversation, type Message } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from '../store';

export default function Messages() {
  const { client, me } = useApp();
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [active, setActive] = useState<Conversation | null>(null);
  const [msgs, setMsgs] = useState<Message[]>([]);
  const [text, setText] = useState('');
  const [warning, setWarning] = useState<string | null>(null);
  const [peer, setPeer] = useState('');

  useEffect(() => {
    void client.conversations().then(setConvs);
  }, [client]);

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
              {c.kind === 'task' ? `📋 任务会话 #${c.task_id}` : `💬 私聊 #${c.id}`}
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
                  {m.content}
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
            <div className="row" style={{ marginTop: 8 }}>
              <input className="grow" value={text} onChange={(e) => setText(e.target.value)}
                     onKeyDown={(e) => e.key === 'Enter' && void send()} placeholder="输入消息…" />
              <button onClick={() => void send()}>发送</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
