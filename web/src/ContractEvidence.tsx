import { useState } from 'react';
import { apiErrorText, type SignatureReport } from '@platform/core';
import { useApp } from './store';

export default function ContractEvidence({ contractId }: { contractId: number }) {
  const { client } = useApp();
  const [report, setReport] = useState<SignatureReport>();
  const [chain, setChain] = useState<Awaited<ReturnType<typeof client.blockchainStatus>>>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  return <div className="evidence-panel">
    <button className="ghost" disabled={busy} onClick={async () => {
      setBusy(true); setError('');
      try {
        const [signatures, blockchain] = await Promise.all([client.contractSignatures(contractId), client.blockchainStatus()]);
        setReport(signatures); setChain(blockchain);
      } catch (e) { setError(apiErrorText(e)); }
      finally { setBusy(false); }
    }}>{busy ? '核验中…' : '查看签署与存证'}</button>
    {error && <p role="alert" className="error">{error}</p>}
    {report && <div>
      <h4>合同版本 v{report.current_version} · {report.signatures.length ? (report.valid ? '签署记录校验通过' : '签署记录校验异常') : '尚未签署'}</h4>
      <p className="muted">{report.reliability_note}</p>
      <code className="evidence-hash">{report.current_document_hash}</code>
      {report.signatures.map(s => <p key={s.id} className="muted">{s.role === 'requester' ? '发布方' : '执行方'} · v{s.contract_version} · {s.provider} · {s.signature_valid ? '记录有效' : '校验失败'}</p>)}
      <h4>外部链存证 · {chain?.verified ? '检查点已确认' : chain?.status === 'unconfigured' ? '待接入' : '尚未通过核验'}</h4>
      <p className="muted">{chain?.note || '当前无法确认链上记录，请稍后重新核验。'}</p>
      {chain?.verified && <p className="muted">网络 {chain.chain_id} · 已确认到存证序号 {chain.seq_to}。这是平台检查点，单份合同仍需结合其存证序号核对覆盖范围。</p>}
    </div>}
  </div>;
}
