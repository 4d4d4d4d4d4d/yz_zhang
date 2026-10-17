import {
  apiErrorText, chinaDateAt, chinaQuarter, chinaToday, fmtYuan,
  type ContractReview, type OpcCalendar, type OpcEntryRow, type OpcProfileView, type OpcSummary,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useApp } from '../store';

/** OPC-100 一人公司：财税与合规（124 号 spec）。
 *
 * 记账底稿（平台收入一键导入）、季度汇总与免税标准提示、申报日历、签约前合同体检。
 * **只出底稿与提醒**：报税、开票、签字由你本人在官方渠道完成。
 */
type Tab = 'books' | 'summary' | 'calendar' | 'contract' | 'profile';
const ENTITY: Record<string, string> = { individual: '个人（没有登记主体）', sole_prop: '个体工商户', company: '公司（含一人有限公司）' };
const VAT: Record<string, string> = { none: '不是增值税纳税人', small_scale: '小规模纳税人', general: '一般纳税人' };
const LEVEL: Record<string, string> = { high: '要改', medium: '注意', info: '提示' };

export default function Opc() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get('tab') as Tab) || 'books';
  return (
    <div className="page workbench">
      <div className="page-heading">
        <h2>一人公司</h2>
        <p className="muted">记账底稿、申报日历、合同体检。只出底稿与提醒：报税、开票、签字由你本人在官方渠道完成。<Link to="/packs?pack=opc-finance-compliance">问财税助手</Link></p>
      </div>
      <div className="row" role="tablist" aria-label="一人公司视图">
        {([['books', '账本'], ['summary', '汇总'], ['calendar', '申报日历'], ['contract', '合同体检'], ['profile', '主体设置']] as [Tab, string][]).map(([t, label]) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? '' : 'ghost'} onClick={() => setParams({ tab: t })}>{label}</button>
        ))}
      </div>
      {tab === 'books' && <Books />}
      {tab === 'summary' && <Summary />}
      {tab === 'calendar' && <Calendar />}
      {tab === 'contract' && <Contract />}
      {tab === 'profile' && <Profile />}
    </div>
  );
}

function Books() {
  const { client } = useApp();
  const [period, setPeriod] = useState(chinaQuarter());
  const [rows, setRows] = useState<OpcEntryRow[]>([]);
  const [form, setForm] = useState({ occurred_on: chinaToday(), kind: 'expense' as 'income' | 'expense', yuan: '', category: '', counterparty: '', invoice_no: '' });
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    try { setRows(await client.opcEntries({ period })); } catch (e) { setError(apiErrorText(e)); }
  }, [client, period]);
  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<string>) {
    setError(''); setNotice('');
    try { setNotice(await fn()); await load(); } catch (e) { setError(apiErrorText(e)); }
  }
  async function exportCsv() {
    try {
      const out = await client.exportOpcBooks(period);
      const url = URL.createObjectURL(new Blob(['﻿' + out.csv], { type: 'text/csv' }));
      const a = document.createElement('a');
      a.href = url; a.download = out.filename; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { setError(apiErrorText(e)); }
  }
  const cents = Math.round(Number(form.yuan) * 100);
  return (
    <div>
      <div className="row">
        <label>期间 <input aria-label="期间" value={period} onChange={(e) => setPeriod(e.target.value.trim())} placeholder="2026-Q3 / 2026-10 / 2026" /></label>
        <button onClick={() => void act(async () => `导入了 ${(await client.importPlatformIncome()).imported} 笔平台收入`)}>导入平台收入</button>
        <button className="ghost" onClick={() => void exportCsv()}>导出 CSV</button>
      </div>
      <div className="card" aria-label="记一笔">
        <div className="row">
          <input type="date" aria-label="日期" value={form.occurred_on} onChange={(e) => setForm({ ...form, occurred_on: e.target.value })} />
          <select aria-label="收支" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as 'income' | 'expense' })}>
            <option value="income">收入</option><option value="expense">支出</option>
          </select>
          <input aria-label="金额（元）" placeholder="含税金额（元）" value={form.yuan} onChange={(e) => setForm({ ...form, yuan: e.target.value })} />
          <input aria-label="类别" placeholder="类别" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
          <input aria-label="对方" placeholder="对方" value={form.counterparty} onChange={(e) => setForm({ ...form, counterparty: e.target.value })} />
          <input aria-label="发票号" placeholder="发票号（没有就空着）" value={form.invoice_no} onChange={(e) => setForm({ ...form, invoice_no: e.target.value })} />
          <button disabled={!(cents > 0)} onClick={() => void act(async () => {
            await client.addOpcEntry({ occurred_on: form.occurred_on, kind: form.kind, amount_cents: cents, category: form.category,
              counterparty: form.counterparty, invoice_no: form.invoice_no, invoice_kind: form.invoice_no ? 'ordinary' : 'none' });
            setForm({ ...form, yuan: '', counterparty: '', invoice_no: '' });
            return '记上了';
          })}>记一笔</button>
        </div>
      </div>
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}
      <table>
        <thead><tr><th>日期</th><th>收支</th><th>金额</th><th>类别</th><th>对方</th><th>发票号</th><th></th></tr></thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={7} className="muted">这个期间还没有账</td></tr>}
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.occurred_on}</td><td>{r.kind === 'income' ? '收入' : '支出'}</td><td>{fmtYuan(r.amount_cents)}</td>
              <td>{r.category}{r.source === 'platform' && <span className="badge">平台</span>}</td><td>{r.counterparty}</td>
              <td>{r.invoice_no || (r.kind === 'expense' ? <span className="error">缺票</span> : '')}
                {!r.invoice_no && <button className="text-link" onClick={() => {
                  const no = window.prompt('发票号');
                  if (no) void act(async () => { await client.updateOpcEntry(r.id, { invoice_no: no }); return '已补发票号'; });
                }}>补</button>}</td>
              <td>{r.source === 'manual' && <button className="danger" onClick={() => void act(async () => { await client.deleteOpcEntry(r.id); return '已删除'; })}>删</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Summary() {
  const { client } = useApp();
  const [period, setPeriod] = useState(chinaQuarter());
  const [s, setS] = useState<OpcSummary | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { client.opcSummary(period).then(setS).catch((e) => setError(apiErrorText(e))); }, [client, period]);
  return (
    <div>
      <label>期间 <input aria-label="汇总期间" value={period} onChange={(e) => setPeriod(e.target.value.trim())} /></label>
      {error && <p className="error">{error}</p>}
      {s && (
        <div className="card" aria-label="汇总">
          <p>收入 <strong>{fmtYuan(s.income_cents)}</strong> · 支出 <strong>{fmtYuan(s.expense_cents)}</strong> · 差额 <strong>{fmtYuan(s.profit_cents)}</strong>
            {s.platform_withheld_cents > 0 && <> · 平台已代扣个税 {fmtYuan(s.platform_withheld_cents)}</>}</p>
          {s.vat_check && (
            <p className={s.vat_check.over ? 'error' : ''}>
              免税标准：{fmtYuan(s.vat_check.sales_cents)} / {fmtYuan(s.vat_check.limit_cents)}（{s.vat_check.period_kind === 'quarter' ? '季度' : '月'}）{s.vat_check.over ? ' 已超过' : ' 未超过'}
            </p>
          )}
          <ul>{s.notes.map((n) => <li key={n}>{n}</li>)}</ul>
          <table><tbody>{s.by_category.map((c) => (
            <tr key={`${c.kind}${c.category}`}><td>{c.kind === 'income' ? '收入' : '支出'}</td><td>{c.category}</td><td>{fmtYuan(c.amount_cents)}</td></tr>
          ))}</tbody></table>
          <p className="muted">{s.disclaimer}</p>
        </div>
      )}
    </div>
  );
}

function Calendar() {
  const { client } = useApp();
  const [cal, setCal] = useState<OpcCalendar | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  useEffect(() => { client.opcCalendar(120).then(setCal).catch((e) => setError(apiErrorText(e))); }, [client]);
  async function toWorkbench(date: string, title: string) {
    setError('');
    try {
      // 截止日北京时间 18:00；提前 3 天提醒（与工作台的提醒同一套）
      await client.createWorkbenchItem({ title, priority: 2, category: '财税', due_at: chinaDateAt(date), remind_at: chinaDateAt(date, '18:00', 3) });
      setNotice(`已放进工作台：${title}（提前 3 天提醒）`);
    } catch (e) { setError(apiErrorText(e)); }
  }
  if (!cal) return error ? <p className="error">{error}</p> : null;
  return (
    <div>
      {!cal.configured && <p className="muted">还没填主体设置，下面按「个人」推算。<Link to="/opc?tab=profile">去填</Link></p>}
      <p className="muted">{cal.notice}</p>
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}
      <ul className="list">
        {cal.items.map((i) => (
          <li key={`${i.date}${i.kind}${i.title}`}><strong>{i.date}</strong> {i.title} <span className="muted">· {i.detail}</span>
            <button className="text-link" onClick={() => void toWorkbench(i.date, i.title)}>放进工作台</button></li>
        ))}
      </ul>
    </div>
  );
}

function Contract() {
  const { client } = useApp();
  const [text, setText] = useState('');
  const [role, setRole] = useState<'party_a' | 'party_b' | 'unknown'>('party_b');
  const [r, setR] = useState<ContractReview | null>(null);
  const [error, setError] = useState('');
  async function run() {
    setError('');
    try { setR(await client.reviewContract(text, role)); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <div>
      <p className="muted">把合同全文贴进来。原文不保存，体检完就丢。</p>
      <textarea aria-label="合同全文" rows={10} value={text} onChange={(e) => setText(e.target.value)} />
      <div className="row">
        <label>我是 <select aria-label="我是" value={role} onChange={(e) => setRole(e.target.value as typeof role)}>
          <option value="party_b">接活的一方（乙方）</option><option value="party_a">委托的一方（甲方）</option><option value="unknown">不确定</option>
        </select></label>
        <button disabled={text.trim().length < 20} onClick={() => void run()}>体检</button>
      </div>
      {error && <p className="error">{error}</p>}
      {r && (
        <div className="card" aria-label="体检结果">
          {!r.findings.length ? <p>按清单没看到明显问题。</p> : (
            <ol>{r.findings.map((f, n) => (
              <li key={n}><span className={f.level === 'high' ? 'badge warn' : 'badge'}>{LEVEL[f.level]}</span> <strong>{f.clause}</strong>：{f.finding}<div className="muted">建议：{f.suggestion}</div></li>
            ))}</ol>
          )}
          {(r.amounts.length > 0 || r.dates.length > 0) && <p className="muted">识别到的金额：{r.amounts.join('、') || '无'}；日期：{r.dates.join('、') || '无'}</p>}
          <p className="muted">{r.disclaimer} <Link to="/publish?category=法律咨询">请律师审阅</Link></p>
        </div>
      )}
    </div>
  );
}

function Profile() {
  const { client } = useApp();
  const [p, setP] = useState<OpcProfileView | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  useEffect(() => { client.opcProfile().then(setP).catch((e) => setError(apiErrorText(e))); }, [client]);
  if (!p) return error ? <p className="error">{error}</p> : null;
  async function save() {
    if (!p) return;
    setError(''); setNotice('');
    try { setP(await client.saveOpcProfile({ entity: p.entity, vat: p.vat, vat_period: p.vat_period, small_low_profit: p.small_low_profit })); setNotice('已保存'); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <div className="card" aria-label="主体设置">
      <label>主体 <select aria-label="主体" value={p.entity} onChange={(e) => setP({ ...p, entity: e.target.value as OpcProfileView['entity'], vat: e.target.value === 'individual' ? 'none' : p.vat })}>
        {Object.entries(ENTITY).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
      <label>增值税 <select aria-label="增值税" value={p.vat} disabled={p.entity === 'individual'} onChange={(e) => setP({ ...p, vat: e.target.value as OpcProfileView['vat'] })}>
        {Object.entries(VAT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
      {p.vat === 'small_scale' && (
        <label>申报周期 <select aria-label="申报周期" value={p.vat_period} onChange={(e) => setP({ ...p, vat_period: e.target.value as 'month' | 'quarter' })}>
          <option value="quarter">按季</option><option value="month">按月</option></select></label>
      )}
      {p.entity === 'company' && (
        <label><input type="checkbox" checked={p.small_low_profit} onChange={() => setP({ ...p, small_low_profit: !p.small_low_profit })} /> 小型微利企业</label>
      )}
      <button onClick={() => void save()}>保存</button>
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
