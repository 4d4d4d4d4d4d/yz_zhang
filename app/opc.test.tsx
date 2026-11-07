// OPC-100 一人公司在 App 上的行为（124 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { OpcScreen } from './opc';

type Call = { method: string; path: string; body?: unknown };
const SUMMARY = { period: '2026-Q4', start: '', end: '', kind: 'quarter', income_cents: 120000, expense_cents: 0, profit_cents: 120000,
  by_category: [], platform_withheld_cents: 0, entries: 1, vat_check: null, notes: ['没有登记为纳税人的个人：平台代扣个税'], disclaimer: '不是申报表' };

function makeClient(routes: Record<string, unknown>, calls: Call[]) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : undefined });
    const hit = Object.keys(routes).find((k) => k === `${method} ${path}`) ?? Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('OPC-100 App 上的一人公司', () => {
  it('导入平台收入、记一笔（元→分），看本季汇总', async () => {
    const calls: Call[] = [];
    const client = makeClient({ '/opc/summary': SUMMARY, 'POST /opc/entries/import-platform': { imported: 3 }, 'POST /opc/entries': { id: 1 } }, calls);
    render(<OpcScreen client={client} />);
    expect(await screen.findByText(/收入 ¥1200.00/)).toBeTruthy();
    fireEvent.press(screen.getByText('导入平台收入'));
    expect(await screen.findByText('导入了 3 笔平台收入')).toBeTruthy();
    fireEvent.changeText(screen.getByPlaceholderText('金额（元）'), '88.8');
    fireEvent.press(screen.getByText('记一笔'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/opc/entries')?.body).toMatchObject({ amount_cents: 8880, kind: 'expense' }));
  });

  it('申报日历放进工作台；合同体检按乙方', async () => {
    const calls: Call[] = [];
    const client = makeClient({ '/opc/summary': SUMMARY,
      '/opc/calendar': { configured: true, notice: '以电子税务局为准', items: [{ date: '2026-10-15', kind: 'vat', title: '申报上季度增值税及附加税费', detail: '' }] },
      'POST /workbench/items': { id: 9 },
      'POST /opc/contract-review': { findings: [{ level: 'high', clause: '违约金', finding: '违约金比例 50% 偏高', suggestion: '协商降低' }], amounts: [], dates: [], disclaimer: '不构成法律意见' },
    }, calls);
    render(<OpcScreen client={client} />);
    fireEvent.press(await screen.findByText('申报日历'));
    fireEvent.press(await screen.findByText('放进工作台（提前 3 天提醒）'));
    await waitFor(() => expect(calls.find((c) => c.path === '/workbench/items')?.body).toMatchObject({ due_at: '2026-10-15T10:00:00.000Z', remind_at: '2026-10-12T10:00:00.000Z' }));
    fireEvent.press(screen.getByText('合同体检'));
    fireEvent.changeText(screen.getByPlaceholderText('合同全文'), '如乙方违约，应支付合同总额 50% 的违约金。');
    fireEvent.press(screen.getByText('体检'));
    expect(await screen.findByText(/违约金比例 50% 偏高/)).toBeTruthy();
    expect(calls.find((c) => c.path === '/opc/contract-review')?.body).toMatchObject({ role: 'party_b' });
  });

  it('主体设置：选个体户后默认小规模，可切按月', async () => {
    const calls: Call[] = [];
    const client = makeClient({ '/opc/summary': SUMMARY,
      'GET /opc/profile': { entity: 'individual', vat: 'none', vat_period: 'quarter', small_low_profit: true, configured: false },
      'PUT /opc/profile': { entity: 'sole_prop', vat: 'small_scale', vat_period: 'month', small_low_profit: true, configured: true } }, calls);
    render(<OpcScreen client={client} />);
    fireEvent.press(await screen.findByText('主体设置'));
    fireEvent.press(await screen.findByText('个体工商户'));
    fireEvent.press(screen.getByText('申报周期：按季 ⇄'));
    fireEvent.press(screen.getByText('保存'));
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT')?.body).toMatchObject({ entity: 'sole_prop', vat: 'small_scale', vat_period: 'month' }));
  });
});
