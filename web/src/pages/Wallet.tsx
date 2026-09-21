import { ApiError, apiErrorText, fmtYuan, formatDate, formatDateTime, ledgerKindLabel, type LedgerRow, type PayoutAccountView, type TaxSummary, type Wallet } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from '../store';

export default function WalletPage() {
  const { client } = useApp();
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [ledger, setLedger] = useState<LedgerRow[]>([]);
  const [amount, setAmount] = useState('100');
  const [error, setError] = useState('');
  const [hint, setHint] = useState('');

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
      setError(apiErrorText(err));
    }
  }

  const cents = Math.round(parseFloat(amount || '0') * 100);

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
          <button className="ghost" onClick={() => act(async () => {
            const r = await client.withdraw(cents);
            // AML-030/031 大额进人审时服务端给的是**中性话术**，原样显示
            setHint(r.status === 'pending_review' ? (r.message ?? '提现申请已提交，等待处理') : '');
          })}>提现</button>
        </div>
        {hint && <p className="muted">{hint}</p>}
        {error && <p className="error">{error}</p>}
      </div>
      <PayoutAccount onBound={load} />
      <div className="card">
        <h3>账单流水</h3>
        <table>
          <thead><tr><th>类型</th><th>金额</th><th>备注</th><th>时间</th></tr></thead>
          <tbody>
            {ledger.map((e) => (
              <tr key={e.id}>
                <td>{ledgerKindLabel(e.kind)}</td>
                <td style={{ color: e.amount_cents >= 0 ? 'var(--ok)' : 'var(--bad)' }}>
                  {e.amount_cents >= 0 ? '+' : ''}{fmtYuan(e.amount_cents)}
                </td>
                <td className="muted">{e.memo}</td>
                <td className="muted">{formatDateTime(e.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <TaxDetail />
    </div>
  );
}

/** PAY-030 收款账户。**提现的前置条件，此前全仓没有任何一个界面能满足它。**
 *
 * 服务端 `POST /wallet/withdraw` 第一行就是「没绑收款账户就拒」，
 * 而 `bindPayoutAccount` 在 Web 和 App 上都没有被调用过一次——
 * 于是提现按钮每一次点击都返回 400，用户看到「请先绑定收款账户」，
 * 然后在整个产品里找不到任何一处可以绑定。**钱能进，不能出。**
 *
 * 回显用的是服务端返回的**脱敏**卡号（`6222****0000`）——
 * 服务端本来就不给完整卡号，这里也不要试图自己拼回去。
 */
function PayoutAccount({ onBound }: { onBound: () => Promise<void> }) {
  const { client } = useApp();
  const [acct, setAcct] = useState<PayoutAccountView | null>(null);
  const [accountNo, setAccountNo] = useState('');
  const [holder, setHolder] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setAcct(await client.getPayoutAccount().catch(() => null));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  return (
    <div className="card">
      <h3>收款账户</h3>
      {acct?.bound ? (
        <p className="muted">已绑定 · {acct.kind === 'alipay' ? '支付宝' : '银行卡'} {acct.account_no}（{acct.holder_name}）</p>
      ) : (
        <p className="muted">未绑定收款账户，提现会被拒绝。</p>
      )}
      <div className="row" style={{ marginTop: 8 }}>
        <input placeholder="银行卡号 / 支付宝账号" value={accountNo} onChange={(e) => setAccountNo(e.target.value)} />
        <input style={{ width: 120 }} placeholder="开户姓名" value={holder} onChange={(e) => setHolder(e.target.value)} />
        <button onClick={async () => {
          setError('');
          try {
            await client.bindPayoutAccount(accountNo.trim(), holder.trim());
            setAccountNo('');
            await load();
            await onBound();
          } catch (err) {
            // AML-012 账户聚集等风控拒绝：理由原样显示（CLI-064）
            setError(apiErrorText(err));
          }
        }}>{acct?.bound ? '更换' : '绑定'}</button>
      </div>
      {/* PAY-005 收款人须与实名一致（防代提/洗钱）。**先说，别让他提交完才知道**——
          `Me` 上没有 real_name（实名是敏感信息，只在数据导出里给），
          所以这里只能提示，填不了默认值。 */}
      <p className="muted">收款人姓名须与实名认证一致，否则会被拒绝。</p>
      {error && <p className="error">{error}</p>}
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
              <td className="muted">{formatDate(t.at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted" style={{ marginTop: 8 }}>{tax.disclaimer}</p>
    </div>
  );
}
