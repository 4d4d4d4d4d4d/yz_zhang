// SCN-205（330 号 spec）建站交付的账号交接清单：执行方在托管期间逐项登记要交给发单人的账号（域名、小程序、
// 服务器、支付商户号），发单人逐项确认「已在我名下」。账号卡在开发方手里是建站最常见的纠纷。
import { apiErrorText, HANDOVER_KIND_LABEL, handoverSummary, type ContractHandoverItem, type HandoverKind } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from './store';

export default function HandoverBlock({ contractId, isExecutor, isRequester, live }: {
  contractId: number; isExecutor: boolean; isRequester: boolean; live: boolean;
}) {
  const { client } = useApp();
  const [rows, setRows] = useState<ContractHandoverItem[]>([]);
  const [kind, setKind] = useState<HandoverKind>('domain');
  const [name, setName] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setRows(await client.contractHandover(contractId).catch(() => []));
  }, [client, contractId]);
  useEffect(() => { void load(); }, [load]);
  const canEdit = isExecutor && live;
  if (rows.length === 0 && !canEdit) return null;
  async function run(fn: () => Promise<ContractHandoverItem[]>) {
    setError('');
    try { setRows(await fn()); } catch (e) { setError(apiErrorText(e)); }
  }
  async function add() {
    if (!name.trim()) { setError('写上账号是什么（比如域名 example.com、某某小店小程序）'); return; }
    await run(() => client.addContractHandover(contractId, { kind, name: name.trim(), note: note.trim() }));
    setName(''); setNote('');
  }
  const summary = handoverSummary(rows);
  return (
    <div aria-label="账号交接" style={{ marginTop: 10 }}>
      <h4>账号交接</h4>
      {summary && <p className={rows.every((r) => r.confirmed_at) ? 'muted' : 'error'} data-testid="handover-summary">{summary}</p>}
      {rows.length === 0 && <p className="muted">域名、小程序、服务器、支付商户号要交给发单人的，逐项登记；发单人确认在自己名下才算交接完。</p>}
      <ul>
        {rows.map((r) => (
          <li key={r.id}>{HANDOVER_KIND_LABEL[r.kind] ?? '其他账号'}：{r.name}{r.note ? `（${r.note}）` : ''}{' '}
            {r.confirmed_at ? <span className="badge">已在发单人名下</span> : <span className="muted">待确认</span>}
            {isRequester && !r.confirmed_at && (
              <button className="text-link" onClick={() => void run(() => client.confirmContractHandover(contractId, r.id))}>已在我名下</button>
            )}
            {canEdit && !r.confirmed_at && (
              <button className="text-link" onClick={() => void run(() => client.removeContractHandover(contractId, r.id))}>删掉</button>
            )}
          </li>
        ))}
      </ul>
      {canEdit && (
        <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
          <select aria-label="账号类别" value={kind} onChange={(e) => setKind(e.target.value as HandoverKind)}>
            {(Object.keys(HANDOVER_KIND_LABEL) as HandoverKind[]).map((k) => <option key={k} value={k}>{HANDOVER_KIND_LABEL[k]}</option>)}
          </select>
          <input aria-label="账号" placeholder="账号（如 example.com）" value={name} onChange={(e) => setName(e.target.value)} />
          <input aria-label="说明" placeholder="说明（可不填：在哪个平台、怎么转移）" value={note} onChange={(e) => setNote(e.target.value)} />
          <button onClick={() => void add()}>登记一项</button>
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
