// GIG-100 接单在 App 上的行为（125 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { DEPART_HINT, departAt, PlatformClient } from '@platform/core';
import { GigScreen } from './gig';

type Call = { method: string; path: string; query: string; body?: unknown };
const OFF = { available: false, until: null, radius_km: null, categories: [], pushed: 0 };
const ON = { available: true, until: '2026-10-13T12:00:00Z', radius_km: 3, categories: [], pushed: 0 };
const CARD = { task_id: 9, title: '两居室保洁', category: '保洁', budget_cents: 15000, net_cents: 13800, address_hint: '人民广场', city: '上海', deadline: null, distance_m: 820 };
const here = async () => ({ lat: 31.2345, lng: 121.4789 });

function makeClient(routes: Record<string, unknown>, calls: Call[]) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const [path, query = ''] = String(url).replace(/^.*\/api\/v1/, '').split('?');
    const method = init?.method ?? 'GET';
    calls.push({ method, path, query, body: init?.body ? JSON.parse(init.body) : undefined });
    const hit = Object.keys(routes).find((k) => k === `${method} ${path}`) ?? Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('GIG-100 App 上的接单', () => {
  it('我现在有空：带上定位与半径', async () => {
    const calls: Call[] = [];
    const client = makeClient({ 'GET /gig/available': OFF, '/gig/places': [], 'PUT /gig/available': ON }, calls);
    render(<GigScreen client={client} locate={here} />);
    fireEvent.press(await screen.findByText('3 公里'));
    fireEvent.press(screen.getByText('我现在有空（2 小时）'));
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({ lat: 31.2345, lng: 121.4789, radius_km: 3, hours: 2 }));
  });

  it('拿不到定位时不发请求，直说', async () => {
    const calls: Call[] = [];
    const client = makeClient({ 'GET /gig/available': OFF, '/gig/places': [] }, calls);
    render(<GigScreen client={client} locate={async () => null} />);
    fireEvent.press(await screen.findByText('我现在有空（2 小时）'));
    expect(await screen.findByText(/没拿到位置/)).toBeTruthy();
    expect(calls.some((c) => c.method === 'PUT')).toBe(false);
  });

  it('有空时列出附近的单、点开任务、看行情；顺路单到公司', async () => {
    const calls: Call[] = [];
    const onOpenTask = jest.fn();
    const client = makeClient({ 'GET /gig/available': ON, '/gig/places': [{ id: 2, name: '公司', lat: 31.23, lng: 121.53 }],
      '/gig/nearby': { radius_km: 3, items: [CARD], notice: '' },
      'POST /gig/quote': { task_id: 9, category: '保洁', city: '上海', sample_size: 3, p50_cents: 20000, min_cents: 1, max_cents: 1,
        budget_cents: 15000, suggested_cents: 20000, net_cents: 18400, basis: ['中位 ¥200.00'], disclaimer: '不是承诺价' },
      '/gig/along': { to: '公司', max_detour_km: 2, notice: '', items: [{ ...CARD, task_id: 10, title: '顺路取件', distance_m: undefined, detour_m: 270 }] } }, calls);
    render(<GigScreen client={client} locate={here} onOpenTask={onOpenTask} />);
    expect(await screen.findByText(/约 0.8 公里 · 到手约 ¥138.00/)).toBeTruthy();
    fireEvent.press(screen.getByText('两居室保洁'));
    expect(onOpenTask).toHaveBeenCalledWith(9);
    fireEvent.press(screen.getByText('看行情'));
    expect(await screen.findByText('· 中位 ¥200.00')).toBeTruthy();
    fireEvent.press(screen.getByText('到公司'));
    fireEvent.press(screen.getByText('从这里出发，看顺路的单'));
    expect(await screen.findByText(/多走约 0.3 公里/)).toBeTruthy();
    expect(calls.find((c) => c.path === '/gig/along')?.query).toContain('to_place=2');
  });
});

describe('SCN-129 App 接单卡片写明名额哪天几点', () => {
  it('按天的名额写日期与时段', async () => {
    const calls: Call[] = [];
    const client = makeClient({ 'GET /gig/available': ON, '/gig/places': [],
      '/gig/nearby': { radius_km: 3, notice: '', items: [{ ...CARD, work_date: '2026-10-24', shift_start: '09:00', shift_end: '18:00' }] } }, calls);
    render(<GigScreen client={client} locate={here} />);
    expect(await screen.findByText(/人民广场 · 10-24 09:00–18:00 · 约 0.8 公里/)).toBeTruthy();
  });
});

describe('SCN-134 App 顺路单可以设出发时间', () => {
  const places = [{ id: 2, name: '公司', lat: 31.23, lng: 121.53 }];
  it('明天 08:30 出发：带上出发时间（之后 3 小时），结果上写明', async () => {
    const calls: Call[] = [];
    const at = departAt(1, '08:30') as string;
    const client = makeClient({ 'GET /gig/available': OFF, '/gig/places': places,
      '/gig/along': { to: '公司', max_detour_km: 2, notice: '', depart_at: at, within_hours: 3, items: [] } }, calls);
    render(<GigScreen client={client} locate={here} />);
    fireEvent.press(await screen.findByText('到公司'));
    fireEvent.press(screen.getByText('明天'));
    fireEvent.changeText(screen.getByLabelText('几点出发'), '08:30');
    fireEvent.press(screen.getByText('从这里出发，看顺路的单'));
    expect(await screen.findByText(`按 ${at.slice(5, 10)} 08:30 出发、之后 3 小时内的名额筛`)).toBeTruthy();
    const q = new URLSearchParams(calls.find((c) => c.path === '/gig/along')?.query ?? '');
    expect([q.get('depart_at'), q.get('within_hours')]).toEqual([at, '3']);
  });

  it('时间写错不发请求，就地说明；空着就按现在', async () => {
    const calls: Call[] = [];
    const client = makeClient({ 'GET /gig/available': OFF, '/gig/places': places,
      '/gig/along': { to: '公司', max_detour_km: 2, notice: '', items: [] } }, calls);
    render(<GigScreen client={client} locate={here} />);
    fireEvent.press(await screen.findByText('到公司'));
    fireEvent.changeText(screen.getByLabelText('几点出发'), '8点半');
    fireEvent.press(screen.getByText('从这里出发，看顺路的单'));
    expect(await screen.findByText(DEPART_HINT)).toBeTruthy();
    expect(calls.some((c) => c.path === '/gig/along')).toBe(false);
    fireEvent.changeText(screen.getByLabelText('几点出发'), '');
    fireEvent.press(screen.getByText('从这里出发，看顺路的单'));
    await waitFor(() => expect(calls.find((c) => c.path === '/gig/along')?.query).not.toContain('depart_at'));
  });
});
