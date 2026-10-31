// OPC-100 一人公司（124 号 spec）：账本、汇总的免税标准、申报日历放进工作台、合同体检。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = {
  id: 2, phone: '138****0002', nickname: '我', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100,
  rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2',
};
type Call = { method: string; path: string; body?: unknown };
const ROW = { id: 1, occurred_on: '2026-08-10', kind: 'expense', amount_cents: 500000, tax_cents: 0, category: '软件订阅',
  counterparty: '某云', invoice_no: '', invoice_kind: 'none', note: '', source: 'manual', created_at: '2026-08-10T00:00:00Z' };

function open(path: string, routes: Record<string, unknown>, calls: Call[] = []) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const key = Object.keys(routes).find((k) => k === `${method} ${p}`) ?? Object.keys(routes).find((k) => k === p);
    return { ok: true, status: 200, text: async () => JSON.stringify(key ? routes[key] : (p === '/users/me' ? ME : [])) };
  }) as unknown as typeof fetch;
  const client = new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
  render(<MemoryRouter initialEntries={[path]}><AppProvider client={client}><App /></AppProvider></MemoryRouter>);
  return calls;
}

describe('OPC-100 一人公司', () => {
  it('账本：导入平台收入、记一笔（元换成分）、缺票的标出来', async () => {
    const calls: Call[] = [];
    open('/opc', { 'GET /opc/entries': [ROW], 'POST /opc/entries/import-platform': { imported: 2 }, 'POST /opc/entries': ROW }, calls);
    expect(await screen.findByText('缺票')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '导入平台收入' }));
    expect((await screen.findByRole('status')).textContent).toContain('导入了 2 笔平台收入');
    fireEvent.change(screen.getByLabelText('金额（元）'), { target: { value: '1234.5' } });
    fireEvent.change(screen.getByLabelText('类别'), { target: { value: '设计费' } });
    fireEvent.click(screen.getByRole('button', { name: '记一笔' }));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/opc/entries')?.body).toMatchObject({ amount_cents: 123450, category: '设计费', kind: 'expense', invoice_kind: 'none' }));
  });

  it('汇总：免税标准与口径出处、免责说明', async () => {
    open('/opc?tab=summary', { '/opc/summary': { period: '2026-Q3', start: '2026-07-01', end: '2026-09-30', kind: 'quarter',
      income_cents: 31000000, expense_cents: 500000, profit_cents: 30500000, by_category: [{ kind: 'income', category: '设计费', amount_cents: 31000000 }],
      platform_withheld_cents: 0, entries: 3, vat_check: { period_kind: 'quarter', sales_cents: 31000000, limit_cents: 30000000, over: true },
      notes: ['本期收入超过免税标准（财政部 税务总局公告2023年第19号，执行至 2027-12-31）'], disclaimer: '这是记账底稿与提醒，不是申报表' } });
    const box = await screen.findByLabelText('汇总');
    expect(box.textContent).toContain('已超过');
    expect(box.textContent).toContain('2023年第19号');
    expect(box.textContent).toContain('不是申报表');
  });

  it('申报日历：放进工作台，截止北京时间 18:00、提前 3 天提醒', async () => {
    const calls: Call[] = [];
    open('/opc?tab=calendar', { '/opc/calendar': { configured: true, notice: '以电子税务局为准',
      items: [{ date: '2026-10-15', kind: 'vat', title: '申报上季度增值税及附加税费', detail: '小规模纳税人' }] },
      'POST /workbench/items': { id: 1 } }, calls);
    fireEvent.click(await screen.findByRole('button', { name: '放进工作台' }));
    await waitFor(() => expect(calls.find((c) => c.path === '/workbench/items')?.body).toMatchObject({
      title: '申报上季度增值税及附加税费', due_at: '2026-10-15T10:00:00.000Z', remind_at: '2026-10-12T10:00:00.000Z', priority: 2 }));
  });

  it('合同体检：按乙方视角，结果分级，给请律师的入口', async () => {
    const calls: Call[] = [];
    open('/opc?tab=contract', { 'POST /opc/contract-review': { amounts: ['50000'], dates: [], disclaimer: '不构成法律意见',
      findings: [{ level: 'high', clause: '知识产权', finding: '成果的权利归对方，但没写付清后才转移', suggestion: '约定付清后转移' }] } }, calls);
    fireEvent.change(await screen.findByLabelText('合同全文'), { target: { value: '甲方委托乙方完成品牌设计，著作权归甲方所有。' } });
    fireEvent.click(screen.getByRole('button', { name: '体检' }));
    const box = await screen.findByLabelText('体检结果');
    expect(box.textContent).toContain('要改');
    expect(calls.find((c) => c.path === '/opc/contract-review')?.body).toMatchObject({ role: 'party_b' });
    expect(screen.getByRole('link', { name: '请律师审阅' }).getAttribute('href')).toContain('/publish?category=');
  });

  it('主体设置：个人不能选纳税人类型，选个体户后能保存', async () => {
    const calls: Call[] = [];
    open('/opc?tab=profile', { 'GET /opc/profile': { entity: 'individual', vat: 'none', vat_period: 'quarter', small_low_profit: true, configured: false },
      'PUT /opc/profile': { entity: 'sole_prop', vat: 'small_scale', vat_period: 'quarter', small_low_profit: true, configured: true } }, calls);
    expect(((await screen.findByLabelText('增值税')) as HTMLSelectElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('主体'), { target: { value: 'sole_prop' } });
    fireEvent.change(screen.getByLabelText('增值税'), { target: { value: 'small_scale' } });
    fireEvent.click(screen.getByRole('button', { name: '保存' }));
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT')?.body).toMatchObject({ entity: 'sole_prop', vat: 'small_scale', vat_period: 'quarter' }));
  });
});
