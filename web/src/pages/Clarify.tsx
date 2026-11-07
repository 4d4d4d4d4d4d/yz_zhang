/** AI-DEC-001（366 号 spec）说一句话发单：助手追问几句把需求问清，再带到发布页预填（发不发由人定）。 */
import { apiErrorText, asList, clarifyProgressLine, clarifyPublishQuery, type ClarifyQuestion, type ClarifyResult } from '@platform/core';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApp } from '../store';

export default function Clarify() {
  const { client } = useApp();
  const navigate = useNavigate();
  const [text, setText] = useState('');
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<Record<string, string>>({});
  const [result, setResult] = useState<ClarifyResult | null>(null);
  const [error, setError] = useState('');
  const ask = (nextAnswers: Record<string, string>) => {
    setError('');
    client.clarifyTask(text.trim(), nextAnswers).then((r) => {
      // APP-091 响应畸形不白屏：缺草稿就当没拿到，说清稍后再试
      if (!r || typeof r !== 'object' || !r.draft) { setError('助手暂时没回上来，请稍后再试'); return; }
      setResult({ ...r, questions: asList<ClarifyQuestion>(r.questions) }); setAnswers(nextAnswers); setPending({});
    })
      .catch((e) => setError(apiErrorText(e)));
  };
  return (
    <div className="page" aria-label="说一句话发单">
      <h1>说一句话，我帮你问清楚</h1>
      <p className="muted">不用想格式：说你要办什么事，我问几句把时间、地点、做到什么程度、怎么验收问清楚，再带到发布页。发不发、怎么改都由你定。</p>
      <textarea aria-label="你要办什么事" placeholder="比如：家里要打扫一下" value={text} maxLength={500}
                onChange={(e) => setText(e.target.value)} />
      <button type="button" disabled={text.trim().length < 2} onClick={() => ask({})}>{result ? '重新开始' : '开始'}</button>
      {error && <p className="error">{error}</p>}
      {result && (
        <div className="card" style={{ marginTop: 8 }}>
          <p role="status">{clarifyProgressLine(result)}</p>
          {result.questions.map((q) => (
            <label key={q.key} style={{ display: 'block' }}>
              {q.ask}{q.required ? '' : '（选答）'}
              {asList<string>(q.options).length ? (
                <select aria-label={q.ask} value={pending[q.key] ?? ''} onChange={(e) => setPending({ ...pending, [q.key]: e.target.value })}>
                  <option value="">— 请选择 —</option>
                  {asList<string>(q.options).map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              ) : (
                <input aria-label={q.ask} value={pending[q.key] ?? ''} maxLength={200}
                       onChange={(e) => setPending({ ...pending, [q.key]: e.target.value })} />
              )}
            </label>
          ))}
          {!!result.questions.length && !result.blocked && (
            <button type="button" onClick={() => ask({ ...answers, ...Object.fromEntries(Object.entries(pending).filter(([, v]) => v.trim())) })}>
              回答
            </button>
          )}
          {result.draft.on_behalf_hint && <p className="muted">说到了家里人：到发布页可以勾「替别人发」，对方的联系方式成交后才给接单的人。</p>}
          {result.ready && (
            <>
              <pre aria-label="草稿" style={{ whiteSpace: 'pre-wrap' }}>{result.draft.description}</pre>
              <button type="button" onClick={() => navigate(`/publish?${clarifyPublishQuery(result.draft)}`)}>带到发布页</button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
