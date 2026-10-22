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
  first_responded: false, first_response_hours: 4, first_response_overdue: true, replies: [],
  category: 'general', priority: 'normal', priority_label: '一般' };

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

  it('ESCA-056 在自己的工单里补充；已结的补充后重新打开', async () => {
    const calls: Call[] = [];
    const done = { ...T, status: 'resolved', escalation_level: 0 };
    const after = { ...done, status: 'open', reopened: true, replies: [{ body: '还是没到账', is_staff: false, created_at: '2026-10-14T00:00:00Z' }] };
    const client = makeClient({ 'GET /support/tickets': [done], 'POST /support/tickets/3/replies': after }, calls);
    render(<SupportTicketsScreen client={client} />);
    fireEvent.changeText(await screen.findByLabelText('补充工单 3'), '还是没到账');
    fireEvent.press(screen.getByText('补充'));
    await waitFor(() => expect(calls.find((c) => c.path === '/support/tickets/3/replies')?.body).toEqual({ body: '还是没到账' }));
    expect(await screen.findByText('已补充，工单 #3 重新打开')).toBeTruthy();
  });

  it('ESCA-059 已结的单只回谢谢：写明保持已解决', async () => {
    const done = { ...T, status: 'resolved', escalation_level: 0 };
    const after = { ...done, reopened: false, kept_closed: true, replies: [{ body: '谢谢', is_staff: false, created_at: '2026-10-14T00:00:00Z' }] };
    const client = makeClient({ 'GET /support/tickets': [done], 'POST /support/tickets/3/replies': after }, []);
    render(<SupportTicketsScreen client={client} />);
    fireEvent.changeText(await screen.findByLabelText('补充工单 3'), '谢谢');
    fireEvent.press(screen.getByText('补充'));
    expect(await screen.findByText('收到，工单 #3 保持已解决；如果问题还在，写清哪里不对就会重新打开')).toBeTruthy();
  });

  it('ESCA-052 选「资金 · 加急」提交带上类别；加急的工单写明', async () => {
    const calls: Call[] = [];
    const client = makeClient({ 'GET /support/tickets': [{ ...T, priority: 'urgent', category: 'funds', priority_label: '加急' }],
      'POST /support/tickets': { id: 4, status: 'open', reply: '', priority: 'urgent' } }, calls);
    render(<SupportTicketsScreen client={client} />);
    expect(await screen.findByText(/提现没到账 · .* · 加急/)).toBeTruthy();
    fireEvent.changeText(screen.getByLabelText('问题概括'), '钱没到');
    fireEvent.press(screen.getByText('资金 · 加急'));
    fireEvent.press(screen.getByText('提交工单'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/support/tickets')?.body).toEqual({ subject: '钱没到', body: '', category: 'funds' }));
  });
});

describe('ESCA-057 App 工单截图', () => {
  it('附截图后提单带上 images；工单里写附了几张', async () => {
    const calls: Array<{ method: string; path: string; body: unknown }> = [];
    const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
      const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
      const method = init?.method ?? 'GET';
      calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
      const body = path === '/files' ? { url: '/api/v1/files/shot1abcdef', ref: 'shot1abcdef' }
        : method === 'GET' && path === '/support/tickets'
          ? [{ id: 3, subject: '页面报错', body: '', status: 'open', reply: '', created_at: '2026-10-13T00:00:00Z', claimed: false,
              escalation_level: 0, escalation_label: '', waited_hours: 1, sla_hours: 24, overdue_hours: 0, first_responded: false,
              first_response_hours: 4, first_response_overdue: false, replies: [], category: 'general', priority: 'normal', priority_label: '一般',
              images: ['/api/v1/files/a', '/api/v1/files/b'] }]
          : { id: 4, status: 'open', reply: '' };
      return { ok: true, status: 200, text: async () => JSON.stringify(body) };
    }) as unknown as typeof fetch;
    render(<SupportTicketsScreen client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })} />);
    expect(await screen.findByText('附 2 张截图')).toBeTruthy();
    fireEvent.changeText(screen.getByLabelText('问题概括'), '提现页面报错');
    fireEvent.press(screen.getByText('附截图（截之前遮住卡号、证件号）'));
    expect(await screen.findByText('再加一张截图（已附 1 张）')).toBeTruthy();
    fireEvent.press(screen.getByText('提交工单'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/support/tickets')?.body)
      .toEqual({ subject: '提现页面报错', body: '', images: ['/api/v1/files/shot1abcdef'] }));
  });
});

describe('ESCA-060 App 自选加急的滥用提示', () => {
  it('选了加急类别才显示提示；提交后的提示里带上这句', async () => {
    const MSG = '你最近 90 天选了加急的 3 张工单里，有 2 张被客服改回了一般。';
    const fetchImpl = (async (url: string, init?: { method?: string }) => {
      const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
      const method = init?.method ?? 'GET';
      const body = path === '/support/tickets/urgent-hint' ? { days: 90, self_urgent: 3, downgraded: 2, message: MSG }
        : method === 'GET' ? [] : { id: 4, status: 'open', reply: '', priority: 'urgent', priority_note: MSG };
      return { ok: true, status: 200, text: async () => JSON.stringify(body) };
    }) as unknown as typeof fetch;
    render(<SupportTicketsScreen client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })} />);
    await screen.findByText('还没有工单。');
    expect(screen.queryByText(MSG)).toBeNull();
    fireEvent.press(screen.getByText('资金 · 加急'));
    expect(await screen.findByText(MSG)).toBeTruthy();
    fireEvent.changeText(screen.getByLabelText('问题概括'), '提现没到账');
    fireEvent.press(screen.getByText('提交工单'));
    expect(await screen.findByText(`已提交。客服回复会发站内信，也会显示在下面。\n${MSG}`)).toBeTruthy();
  });
});
