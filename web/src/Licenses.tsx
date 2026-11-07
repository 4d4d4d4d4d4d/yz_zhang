// SCN-202（329 号 spec）交付附授权清单：执行方在托管期间逐项登记用到的音乐、素材、字体、模板与授权来源；
// 合约双方都看得到。剪辑、建站这类活的交付物里夹着别人的作品，写在聊天里查不到、对不上。
import { apiErrorText, LICENSE_KIND_LABEL, licenseLine, type ContractLicenseItem, type LicenseKind } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from './store';

export default function LicensesBlock({ contractId, isExecutor, live }: { contractId: number; isExecutor: boolean; live: boolean }) {
  const { client } = useApp();
  const [rows, setRows] = useState<ContractLicenseItem[]>([]);
  const [kind, setKind] = useState<LicenseKind>('music');
  const [title, setTitle] = useState('');
  const [source, setSource] = useState('');
  const [scope, setScope] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setRows(await client.contractLicenses(contractId).catch(() => []));
  }, [client, contractId]);
  useEffect(() => { void load(); }, [load]);
  const canEdit = isExecutor && live;
  if (rows.length === 0 && !canEdit) return null;
  async function add() {
    setError('');
    if (!title.trim() || source.trim().length < 2) { setError('写上名称和授权来源（比如「客户提供」「某曲库商用授权」「开源 MIT」）'); return; }
    try {
      setRows(await client.addContractLicense(contractId, { kind, title: title.trim(), source: source.trim(), scope: scope.trim() }));
      setTitle(''); setSource(''); setScope('');
    } catch (e) { setError(apiErrorText(e)); }
  }
  async function remove(id: number) {
    setError('');
    try { setRows(await client.removeContractLicense(contractId, id)); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <div aria-label="授权清单" style={{ marginTop: 10 }}>
      <h4>授权清单</h4>
      {rows.length === 0 && <p className="muted">交付物里用到别人的音乐、素材、字体、模板，在这里逐项写清授权来源。</p>}
      <ul>
        {rows.map((r) => (
          <li key={r.id}>{licenseLine(r)}
            {canEdit && <button className="text-link" onClick={() => void remove(r.id)}>删掉</button>}</li>
        ))}
      </ul>
      {canEdit && (
        <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
          <select aria-label="授权类别" value={kind} onChange={(e) => setKind(e.target.value as LicenseKind)}>
            {(Object.keys(LICENSE_KIND_LABEL) as LicenseKind[]).map((k) => <option key={k} value={k}>{LICENSE_KIND_LABEL[k]}</option>)}
          </select>
          <input aria-label="名称" placeholder="名称（如《夏日》、思源黑体）" value={title} onChange={(e) => setTitle(e.target.value)} />
          <input aria-label="授权来源" placeholder="授权来源（客户提供 / 某曲库商用授权 / 开源 MIT）" value={source} onChange={(e) => setSource(e.target.value)} />
          <input aria-label="授权范围" placeholder="授权范围（可不填：仅限某平台、商用、期限）" value={scope} onChange={(e) => setScope(e.target.value)} />
          <button onClick={() => void add()}>登记一项</button>
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
