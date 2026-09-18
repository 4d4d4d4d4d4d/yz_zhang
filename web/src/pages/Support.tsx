import { useState } from 'react';
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
    </div>
  );
}
