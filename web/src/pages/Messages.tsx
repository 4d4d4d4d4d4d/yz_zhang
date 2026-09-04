import { type Conversation, type Message } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from '../store';

export default function Messages() {
  const { client, me } = useApp();
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [active, setActive] = useState<Conversation | null>(null);
  const [msgs, setMsgs] = useState<Message[]>([]);
  const [text, setText] = useState('');
  const [warning, setWarning] = useState<string | null>(null);

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
          {convs.length === 0 && <p className="muted">暂无会话（成交后自动创建任务会话）</p>}
          {convs.map((c) => (
            <a key={c.id} onClick={() => void openConv(c)} style={{ cursor: 'pointer' }}>
              {c.kind === 'task' ? `📋 任务会话 #${c.task_id}` : `💬 私聊 #${c.id}`}
            </a>
          ))}
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
