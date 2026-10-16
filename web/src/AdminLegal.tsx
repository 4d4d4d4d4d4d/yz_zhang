import { apiErrorText, formatDateTime, type LegalFaqRow, type RadarSignal } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from './store';

/** LAW-060 / SCN-114 法律常识库的运营草稿流（163 号 spec）：合规管理员起草 → 提交 → 另一位合规上线 → 下线写理由。
 *  雷达上「法律问答答不上」的主题可以一键起草：回答与出处留「【待填写】」，填完才能提交。 */
const STATUS: Record<string, string> = { draft: '草稿', review: '待审核', published: '已上线', retired: '已下线' };
const EMPTY = { id: 0, topic: '', keywords: '', answer: '', source: '' };

export function LegalFaqAdmin() {
  const { client, me } = useApp();
  const [rows, setRows] = useState<LegalFaqRow[]>([]);
  const [gaps, setGaps] = useState<RadarSignal[]>([]);
  const [topic, setTopic] = useState('');
  const [form, setForm] = useState(EMPTY);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try { setRows(await client.adminLegalFaqs()); } catch (e) { setError(apiErrorText(e)); return; }
    // 雷达是运营角色看的；合规管理员没有运营角色时就手填主题（服务端照样只认雷达上真有的主题）
    try { setGaps((await client.adminPackRadar()).filter((x) => x.source === 'legal_gap')); } catch { setGaps([]); }
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<unknown>, done: string) {
    setError(''); setNotice('');
    try { await fn(); if (done) setNotice(done); await load(); } catch (e) { setError(apiErrorText(e)); }
  }
  const edit = (r: LegalFaqRow) => setForm({ id: r.id, topic: r.topic, keywords: r.keywords.join('，'), answer: r.answer, source: r.source });
  const draftFrom = (t: string) => act(async () => {
    const r = await client.adminLegalFaqFromRadar(t);
    edit(r);
    setNotice(`已起草「${t}」：把「【待填写】」的回答与出处写完再提交审核`);
  }, '');
  const input = () => ({ topic: form.topic.trim(), keywords: form.keywords.split(/[,，、\s]+/).filter(Boolean),
    answer: form.answer, source: form.source });

  return (
    <div className="card" aria-label="法律知识运营">
      <h3>法律知识（法律问答的知识库）</h3>
      <p className="muted">上线要另一位合规管理员审核（写它的人不能自己批）；起草留的「【待填写】」不写完不能提交；下线要写理由。</p>
      <table>
        <thead><tr><th>主题</th><th>关键词</th><th>状态</th><th>出处</th><th></th></tr></thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={5} className="muted">还没有运营补的条目（代码里的四条照常在用）</td></tr>}
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.topic || '—'}<div className="muted">{r.origin.startsWith('radar:') ? '雷达起草' : '手写'}</div></td>
              <td>{r.keywords.join('、')}</td>
              <td>{STATUS[r.status]}{r.published_at && <div className="muted">{formatDateTime(r.published_at)}</div>}
                {r.retired_reason && <div className="muted">{r.retired_reason}</div>}
                {r.placeholders.length > 0 && <div className="error">{r.placeholders.join('、')}还没填</div>}</td>
              <td className="muted">{r.source}</td>
              <td className="row">
                {r.status === 'draft' && <>
                  <button className="ghost" onClick={() => edit(r)}>编辑</button>
                  <button onClick={() => void act(() => client.adminSubmitLegalFaq(r.id), '已提交审核')}>提交审核</button>
                </>}
                {r.status === 'review' && <>
                  <button disabled={r.created_by === me?.id} title={r.created_by === me?.id ? '写它的人不能自己批' : ''}
                    onClick={() => void act(() => client.adminApproveLegalFaq(r.id), '已上线')}>上线</button>
                  <button className="ghost" onClick={() => void act(() => client.adminRejectLegalFaq(r.id), '已退回草稿')}>退回</button>
                </>}
                {r.status !== 'retired' && (
                  <button className="danger" onClick={() => {
                    const reason = window.prompt('下线理由（会留在记录里）');
                    if (reason && reason.trim().length >= 2) void act(() => client.adminRetireLegalFaq(r.id, reason.trim()), '已下线');
                  }}>下线</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h4>从雷达起草</h4>
      {gaps.map((g) => (
        <div key={g.key} className="row">
          <span className="grow">{g.title}<span className="muted">（{g.evidence}）</span></span>
          <button className="ghost" onClick={() => void draftFrom(g.key)}>起草法律知识</button>
        </div>
      ))}
      <div className="row">
        <input aria-label="法律主题" placeholder="雷达上的主题，例如：婚姻家庭" value={topic} onChange={(e) => setTopic(e.target.value)} />
        <button className="ghost" disabled={!topic.trim()} onClick={() => void draftFrom(topic.trim())}>按主题起草</button>
      </div>

      <h4>{form.id ? `编辑草稿 #${form.id}` : '新写一条'}</h4>
      <input aria-label="主题" placeholder="主题（可空）" value={form.topic} onChange={(e) => setForm({ ...form, topic: e.target.value })} />
      <input aria-label="关键词" placeholder="关键词，逗号分开：用户问题里出现就匹配" value={form.keywords} onChange={(e) => setForm({ ...form, keywords: e.target.value })} />
      <textarea aria-label="回答" rows={5} value={form.answer} onChange={(e) => setForm({ ...form, answer: e.target.value })} />
      <input aria-label="出处" placeholder="出处：法规名与条号或官方链接" value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} />
      <div className="row">
        <button disabled={!form.keywords.trim() || form.answer.trim().length < 10 || form.source.trim().length < 2}
          onClick={() => void act(async () => {
            if (form.id) await client.adminUpdateLegalFaq(form.id, input()); else await client.adminCreateLegalFaq(input());
            setForm(EMPTY);
          }, form.id ? '草稿已保存' : '已存为草稿')}>{form.id ? '保存草稿' : '存为草稿'}</button>
        {form.id > 0 && <button className="ghost" onClick={() => setForm(EMPTY)}>取消编辑</button>}
      </div>
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
