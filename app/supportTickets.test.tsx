// CS-013 / ESCA-051 App 上的我的工单（150 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, type MyTicket } from '@platform/core';
import { SupportTicketsScreen, ticketProgress } from './supportTickets';

type Call = { method: string; path: string; body: unknown };
function makeClient(routes: Record<string, unknown>, calls: Call[]) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    const hit = Object.keys(routes).find((k) => k === `${method} ${path}`) ?? Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : {}) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

const T: MyTicket = { id: 3, subject: '提现没到账', body: '三天了', status: 'open', reply: '', created_at: '2026-10-13T00:00:00Z',
  claimed: true, escalation_level: 2, escalation_label: '已升级给主管', waited_hours: 49, sla_hours: 24, overdue_hours: 25,
  first_responded: false, first_response_hours: 4, first_response_overdue: true, replies: [] };

describe('ESCA-051 App 上的我的工单', () => {
  it('处理进度：有没有人接手、等了多久、是否已升级；结了单的不显示进度', () => {
    expect(ticketProgress(T)).toBe('已有客服接手 · 已等 49 小时（承诺 24 小时内处理） · 已升级给客服主管跟进');
    expect(ticketProgress({ ...T, claimed: false, escalation_level: 1 })).toContain('排队等待客服接手');
    expect(ticketProgress({ ...T, claimed: false, escalation_level: 1 })).toContain('已超时，已催办');
    expect(ticketProgress({ ...T, status: 'resolved' })).toBe('');
  });

  it('列出工单与客服回复，提交新工单后刷新', async () => {
    const calls: Call[] = [];
    const client = makeClient({ 'GET /support/tickets': [T, { ...T, id: 4, subject: '发票', status: 'resolved', reply: '已重开' }],
      'POST /support/tickets': { id: 5, status: 'open', reply: '' } }, calls);
    render(<SupportTicketsScreen client={client} />);
    expect(await screen.findByText(/已升级给客服主管跟进/)).toBeTruthy();
    expect(screen.getByText('客服回复：已重开')).toBeTruthy();
    fireEvent.changeText(screen.getByLabelText('问题概括'), '账户被冻结');
    fireEvent.press(screen.getByText('提交工单'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/support/tickets'
      && (c.body as { subject: string }).subject === '账户被冻结')).toBe(true));
    expect(await screen.findByText(/已提交/)).toBeTruthy();
    expect(calls.filter((c) => c.method === 'GET' && c.path === '/support/tickets').length).toBe(2);
  });
});

describe('ESCA-053 App 上的往来记录（157 号 spec）', () => {
  it('客服回过话的写明「客服已回复」，多条往来都列出来', async () => {
    expect(ticketProgress({ ...T, first_responded: true })).toContain('已有客服接手 · 客服已回复');
    const calls: Call[] = [];
    const replies = [{ body: '在查了', is_staff: true, created_at: '2026-10-14T01:00:00Z' },
      { body: '银行退回了，已重新打款', is_staff: true, created_at: '2026-10-14T05:00:00Z' }];
    const client = makeClient({ 'GET /support/tickets': [{ ...T, first_responded: true, reply: '银行退回了，已重新打款', replies }] }, calls);
    render(<SupportTicketsScreen client={client} />);
    expect(await screen.findByText(/客服（.*）：在查了/)).toBeTruthy();
    expect(screen.getByText(/客服（.*）：银行退回了，已重新打款/)).toBeTruthy();
  });
});
