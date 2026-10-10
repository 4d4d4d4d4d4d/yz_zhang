import { ChainEntry } from './ChainEntry';
import { useState } from 'react';
import { Button, Text, View } from 'react-native';
import { apiErrorText, type PlatformClient, type SignatureReport } from '@platform/core';

export function ContractEvidence({ client, contractId }: { client: PlatformClient; contractId: number }) {
  const [report, setReport] = useState<SignatureReport>();
  const [chain, setChain] = useState<Awaited<ReturnType<PlatformClient['blockchainStatus']>>>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  return <View style={{ gap: 8, paddingVertical: 12 }}>
    <Button title={busy ? '核验中…' : '查看签署与存证'} disabled={busy} onPress={async () => {
      setBusy(true); setError('');
      try {
        const [r, c] = await Promise.all([client.contractSignatures(contractId), client.blockchainStatus()]);
        setReport(r); setChain(c);
      } catch (e) { setError(apiErrorText(e)); }
      finally { setBusy(false); }
    }} />
    {!!error && <Text accessibilityRole="alert">{error}</Text>}
    {report && <>
      <Text>版本 v{report.current_version} · {report.signatures.length ? (report.valid ? '签署记录校验通过' : '签署记录校验异常') : '尚未签署'}</Text>
      <Text>{report.reliability_note}</Text>
      <Text selectable>{report.current_document_hash}</Text>
      <ChainEntry agreement={`0x${report.current_document_hash}`} reference={`opc-contract:${contractId}:v${report.current_version}`} />
      <Text>外部链存证：{chain?.verified ? `已确认到存证序号 ${chain.seq_to}` : chain?.status === 'unconfigured' ? '待接入' : '尚未通过核验'}</Text>
      <Text>{chain?.note}</Text>
    </>}
  </View>;
}
