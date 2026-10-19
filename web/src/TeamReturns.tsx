// TEAM-070（226 号 spec）钱包页「团队拨款」：团队拨给我、没用完的可以退回（离开了团队也能退）。
import { OperationKey, TEAM_RETURN_HINT, apiErrorText, teamReturnedNotice, teamReturnLine, type ReturnableTeamSpend } from '@platform/core';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useApp } from './store';

export function TeamReturns({ onChanged }: { onChanged: () => void }) {
  const { client } = useApp();
  const [rows, setRows] = useState<ReturnableTeamSpend[]>([]);
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  // 每笔拨款一把「这次操作」的键：断网后再点是重试，钱只退一次（104 号）
  const keys = useRef(new Map<number, OperationKey>());

  const load = useCallback(async () => {
    const r = await client.returnableTeamSpends().catch(() => []);
    setRows(Array.isArray(r) ? r : []);
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function giveBack(r: ReturnableTeamSpend) {
    setError(''); setNotice('');
    const cents = Math.round(parseFloat(amounts[r.id] ?? String(r.returnable_cents / 100)) * 100);
    if (!(cents > 0)) { setError('退回金额要大于 0'); return; }
    if (!keys.current.has(r.id)) keys.current.set(r.id, new OperationKey());
    try {
      const out = await keys.current.get(r.id)!.run(`${r.id}:${cents}`, (k) => client.returnTeamSpend(r.team_id, r.id, cents, k));
      setNotice(teamReturnedNotice(cents, out));
      setAmounts((a) => { const n = { ...a }; delete n[r.id]; return n; });
      await load();
      onChanged();
    } catch (e) { setError(apiErrorText(e)); }
  }

  if (rows.length === 0 && !notice) return null;
  return (
    <div className="card" aria-label="团队拨款">
      <h3>团队拨款</h3>
      <p className="muted">{TEAM_RETURN_HINT}</p>
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}
      {rows.map((r) => (
        <div className="row" key={r.id} data-testid={`team-return-${r.id}`}>
          <span className="grow">{teamReturnLine(r)}</span>
          <input style={{ width: 100 }} type="number" min={0.01} step={0.01} aria-label={`退回金额 ${r.id}`}
                 value={amounts[r.id] ?? String(r.returnable_cents / 100)}
                 onChange={(e) => setAmounts({ ...amounts, [r.id]: e.target.value })} />
          <button className="ghost" onClick={() => void giveBack(r)}>退回团队</button>
        </div>
      ))}
    </div>
  );
}
