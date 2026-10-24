import { apiErrorText, type SkillConceptAdminView } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from './store';

/** SKL-101 技能概念表运营（135 号 spec）：看生效的概念、增改别名、下线。改动进审计。 */
export function SkillConceptsAdmin() {
  const { client } = useApp();
  const [view, setView] = useState<SkillConceptAdminView | null>(null);
  const [name, setName] = useState('');
  const [aliases, setAliases] = useState('');
  const [q, setQ] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    try { const v = await client.adminSkillConcepts(); setView(v && Array.isArray(v.effective) ? v : null); } catch (e) { setError(apiErrorText(e)); }
  }, [client]);
  useEffect(() => { void load(); }, [load]);
  async function act(fn: () => Promise<unknown>, done: string) {
    setError(''); setNotice('');
    try { await fn(); setNotice(done); await load(); } catch (e) { setError(apiErrorText(e)); }
  }
  const shown = (view?.effective ?? []).filter((c) => !q || c.name.includes(q) || c.aliases.some((a) => a.includes(q)));
  return (
    <div className="card" aria-label="技能概念表">
      <h3>技能概念表</h3>
      <p className="muted">同一件事的不同说法归到一个规范名：撮合、认技能、个人空间匹配、知识库检索都按它算。一个写法只能属于一个概念。</p>
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}
      <div className="row">
        <input aria-label="规范名" placeholder="规范名，例如：品牌设计" value={name} onChange={(e) => setName(e.target.value)} />
        <input className="grow" aria-label="别名" placeholder="别名，用、分隔" value={aliases} onChange={(e) => setAliases(e.target.value)} />
        <button disabled={!name.trim()} onClick={() => void act(() => client.upsertSkillConcept(name.trim(), aliases.split(/[、,，]+/).map((x) => x.trim()).filter(Boolean)), `已保存「${name.trim()}」`)}>保存</button>
      </div>
      <input aria-label="查概念" placeholder="查一个写法" value={q} onChange={(e) => setQ(e.target.value)} />
      <ul className="list">
        {shown.slice(0, 50).map((c) => {
          const row = view?.overrides.find((o) => o.name === c.name && o.status === 'active');
          return (
            <li key={c.name}><strong>{c.name}</strong> <span className="muted">{c.aliases.join('、')}</span>
              {' '}<button className="text-link" onClick={() => { setName(c.name); setAliases(c.aliases.join('、')); }}>改</button>
              {row && <button className="text-link" onClick={() => void act(() => client.retireSkillConcept(row.id), `已下线「${c.name}」`)}>下线</button>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
