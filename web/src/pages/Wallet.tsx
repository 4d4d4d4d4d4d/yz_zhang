import { ApiError, fmtYuan, type TaxSummary, type Wallet } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from '../store';

export default function WalletPage() {
  const { client } = useApp();
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [ledger, setLedger] = useState<Array<{ id: number; kind: string; amount_cents: number; memo: string; created_at: string }>>([]);
  const [amount, setAmount] = useState('100');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setWallet(await client.wallet());
    setLedger(await client.ledger());
  }, [client]);

  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<unknown>) {
    setError('');
    try {
      await fn();
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '网络错误');
    }
  }

  const cents = Math.round(parseFloat(amount || '0') * 100);
  const KIND_LABEL: Record<string, string> = {
    topup: '充值', withdraw: '提现', escrow_hold: '资金托管', escrow_release: '任务收入',
    refund: '退款', fee: '平台佣金', dispute_split: '纠纷分割',
    tax_withheld: '代扣个人所得税',
  };

  return (
    <div className="page">
      <div className="card">
        <h3>我的钱包</h3>
        {wallet && (
          <div className="row" style={{ gap: 32, margin: '12px 0' }}>
            <div><p className="muted">可用余额</p><h2>{fmtYuan(wallet.available_cents)}</h2></div>
            <div><p className="muted">托管中</p><h2>{fmtYuan(wallet.escrow_cents)}</h2></div>
            <div><p className="muted">冻结中</p><h2>{fmtYuan(wallet.frozen_cents)}</h2></div>
          </div>
        )}
        <div className="row">
          <input style={{ width: 120 }} type="number" min={0.01} step={0.01} value={amount} onChange={(e) => setAmount(e.target.value)} />
          <button onClick={() => act(() => client.topup(cents))}>充值（模拟）</button>
          <button className="ghost" onClick={() => act(() => client.withdraw(cents))}>提现</button>
        </div>
        {error && <p className="error">{error}</p>}
      </div>
      <div className="card">
        <h3>账单流水</h3>
        <table>
          <thead><tr><th>类型</th><th>金额</th><th>备注</th><th>时间</th></tr></thead>
          <tbody>
            {ledger.map((e) => (
              <tr key={e.id}>
                <td>{KIND_LABEL[e.kind] ?? e.kind}</td>
                <td style={{ color: e.amount_cents >= 0 ? 'var(--ok)' : 'var(--bad)' }}>
                  {e.amount_cents >= 0 ? '+' : ''}{fmtYuan(e.amount_cents)}
                </td>
                <td className="muted">{e.memo}</td>
                <td className="muted">{new Date(e.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <TaxDetail />
    </div>
  );
}

/** TAX-021 代扣明细。措辞是刻意的：预扣预缴不是完税，别让用户以为能直接抵扣。 */
function TaxDetail() {
  const { client } = useApp();
  const [tax, setTax] = useState<TaxSummary | null>(null);
  useEffect(() => { void client.myTax().then(setTax).catch(() => {}); }, [client]);
  if (!tax || tax.items.length === 0) return null;
  return (
    <div className="card">
      <h3>个人所得税代扣明细</h3>
      {tax.yearly.map((y) => (
        <p className="muted" key={y.year}>
          {y.year} 年：收入 {fmtYuan(y.income_cents)} · 已代扣 {fmtYuan(y.withheld_cents)}
          （{y.count} 笔）
        </p>
      ))}
      <table style={{ marginTop: 8 }}>
        <thead><tr><th>合约</th><th>收入</th><th>计税基数</th><th>代扣</th><th>时间</th></tr></thead>
        <tbody>
          {tax.items.map((t) => (
            <tr key={t.id}>
              <td>#{t.contract_id}</td>
              <td>{fmtYuan(t.income_cents)}</td>
              <td className="muted">{fmtYuan(t.taxable_cents)}</td>
              <td style={{ color: 'var(--bad)' }}>-{fmtYuan(t.withheld_cents)}</td>
              <td className="muted">{new Date(t.at).toLocaleDateString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted" style={{ marginTop: 8 }}>{tax.disclaimer}</p>
    </div>
  );
}
