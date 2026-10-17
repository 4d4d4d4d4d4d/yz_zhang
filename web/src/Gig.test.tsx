// GIG-100 接单（125 号 spec）：现在有空（拿定位）、附近的单与行情、顺路单、存常用地点。
import { DEPART_HINT, departAt, PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = {
  id: 2, phone: '138****0002', nickname: '我', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100,
  rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2',
};
type Call = { method: string; path: string; query: string; body?: unknown };
const OFF = { available: false, until: null, radius_km: null, categories: [], pushed: 0 };
const ON = { available: true, until: '2026-10-13T12:00:00Z', radius_km: 3, categories: ['保洁'], pushed: 1 };
const CARD = { task_id: 9, title: '两居室保洁', category: '保洁', budget_cents: 15000, net_cents: 13800, address_hint: '人民广场', city: '上海', deadline: null, distance_m: 820 };

function mockGeo() {
  Object.defineProperty(navigator, 'geolocation', { configurable: true, value: {
    getCurrentPosition: (ok: (p: { coords: { latitude: number; longitude: number } }) => void) => ok({ coords: { latitude: 31.2345, longitude: 121.4789 } }),
  } });
}
afterEach(() => { Object.defineProperty(navigator, 'geolocation', { configurable: true, value: undefined }); });

function open(path: string, routes: Record<string, unknown>, calls: Call[] = []) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const [p0, query = ''] = String(url).replace(/^.*\/api\/v1/, '').split('?');
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p0, query, body: init?.body ? JSON.parse(init.body) : undefined });
    const key = Object.keys(routes).find((k) => k === `${method} ${p0}`) ?? Object.keys(routes).find((k) => k === p0);
    return { ok: true, status: 200, text: async () => JSON.stringify(key ? routes[key] : (p0 === '/users/me' ? ME : [])) };
  }) as unknown as typeof fetch;
  const client = new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
  render(<MemoryRouter initialEntries={[path]}><AppProvider client={client}><App /></AppProvider></MemoryRouter>);
  return calls;
}

describe('GIG-100 接单', () => {
  it('我现在有空：拿定位、带上半径时长类目；之后列出附近的单与到手', async () => {
    mockGeo();
    const calls: Call[] = [];
    let state: unknown = OFF;
    const routes: Record<string, unknown> = { '/gig/places': [], '/gig/nearby': { radius_km: 3, items: [CARD], notice: '' } };
    Object.defineProperty(routes, 'GET /gig/available', { enumerable: true, get: () => state });
    Object.defineProperty(routes, 'PUT /gig/available', { enumerable: true, get: () => { state = ON; return ON; } });
    open('/gig', routes, calls);
    fireEvent.change(await screen.findByLabelText('半径'), { target: { value: '3' } });
    fireEvent.change(screen.getByLabelText('只看这些类目'), { target: { value: '保洁 跑腿' } });
    fireEvent.click(screen.getByRole('button', { name: '我现在有空' }));
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({ lat: 31.2345, lng: 121.4789, radius_km: 3, hours: 2, categories: ['保洁', '跑腿'] }));
    expect(await screen.findByRole('link', { name: '两居室保洁' })).toBeTruthy();
    expect(screen.getByText(/约 0.8 公里 · 预算 ¥150.00，到手约 ¥138.00/)).toBeTruthy();
  });

  it('看行情：给出成交分布与到手', async () => {
    open('/gig', { 'GET /gig/available': ON, '/gig/places': [], '/gig/nearby': { radius_km: 3, items: [CARD], notice: '' },
      'POST /gig/quote': { task_id: 9, category: '保洁', city: '上海', sample_size: 3, p50_cents: 20000, min_cents: 10000, max_cents: 30000,
        budget_cents: 15000, suggested_cents: 20000, net_cents: 18400, basis: ['上海·保洁近 180 天 3 单成交，中位 ¥200.00'], disclaimer: '不是承诺价' } });
    fireEvent.click(await screen.findByRole('button', { name: '看行情' }));
    const box = await screen.findByLabelText('报价参考');
    expect(box.textContent).toContain('中位 ¥200.00');
    expect(box.textContent).toContain('不是承诺价');
  });

  it('把这里存为「家」；顺路单从当前位置到公司，按多走的路列出', async () => {
    mockGeo();
    const calls: Call[] = [];
    const places = [{ id: 2, name: '公司', lat: 31.23, lng: 121.53 }];
    open('/gig', { 'GET /gig/available': OFF, 'GET /gig/places': places, 'POST /gig/places': { id: 3, name: '家', lat: 31.23, lng: 121.48 },
      '/gig/along': { to: '公司', max_detour_km: 2, notice: '', items: [{ ...CARD, distance_m: undefined, detour_m: 270, from_start_m: 2800 }] } }, calls);
    fireEvent.click(await screen.findByRole('button', { name: '把这里存为「家」' }));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/gig/places')?.body).toEqual({ name: '家', lat: 31.2345, lng: 121.4789 }));
    fireEvent.change(screen.getByLabelText('终点'), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: '看看顺路的单' }));
    expect(await screen.findByText(/多走约 0.3 公里/)).toBeTruthy();
    const q = calls.find((c) => c.path === '/gig/along')?.query ?? '';
    expect(q).toContain('to_place=2');
    expect(q).toContain('from_lat=31.2345');
  });

  it('拿不到定位时直说', async () => {
    open('/gig', { 'GET /gig/available': OFF, '/gig/places': [] });
    fireEvent.click(await screen.findByRole('button', { name: '我现在有空' }));
    expect((await screen.findByText(/拿不到位置/))).toBeTruthy();
  });
});

describe('SCN-129 接单卡片写明名额哪天几点', () => {
  it('按天的名额写日期与时段，没写时段写全天，不按天的单不写', async () => {
    const slots = [{ ...CARD, task_id: 21, title: '周末快闪店帮手 · 第1天', work_date: '2026-10-24', shift_start: '09:00', shift_end: '18:00' },
      { ...CARD, task_id: 22, title: '展会帮手', work_date: '2026-10-25', shift_start: '', shift_end: '' },
      { ...CARD, task_id: 23, title: '不按天', work_date: null, shift_start: '', shift_end: '' }];
    open('/gig', { 'GET /gig/available': ON, '/gig/places': [], '/gig/nearby': { radius_km: 3, items: slots, notice: '' } });
    expect(await screen.findByText(/人民广场 · 10-24 09:00–18:00 · 约 0.8 公里/)).toBeTruthy();
    expect(screen.getByText(/人民广场 · 10-25 全天 · 约 0.8 公里/)).toBeTruthy();
    const plain = screen.getByRole('link', { name: '不按天' }).parentElement!;
    expect(plain.textContent).toContain('人民广场 · 约 0.8 公里');
  });
});

describe('SCN-134 顺路单可以设出发时间', () => {
  const places = [{ id: 2, name: '公司', lat: 31.23, lng: 121.53 }];
  it('明天 08:30 出发、之后 2 小时：带上出发时间，结果上写明按什么筛的', async () => {
    mockGeo();
    const calls: Call[] = [];
    const at = departAt(1, '08:30') as string;
    open('/gig', { 'GET /gig/available': OFF, 'GET /gig/places': places,
      '/gig/along': { to: '公司', max_detour_km: 2, notice: '', depart_at: at, within_hours: 2, items: [{ ...CARD, distance_m: undefined, detour_m: 270 }] } }, calls);
    fireEvent.change(await screen.findByLabelText('终点'), { target: { value: '2' } });
    expect(screen.queryByLabelText('几点出发')).toBeNull();
    fireEvent.change(screen.getByLabelText('什么时候出发'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('几点出发'), { target: { value: '08:30' } });
    fireEvent.change(screen.getByLabelText('出发后几小时内'), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: '看看顺路的单' }));
    expect(await screen.findByText(`按 ${at.slice(5, 10)} 08:30 出发、之后 2 小时内的名额筛`)).toBeTruthy();
    const q = new URLSearchParams(calls.find((c) => c.path === '/gig/along')?.query ?? '');
    expect([q.get('depart_at'), q.get('within_hours')]).toEqual([at, '2']);
  });

  it('选了今天却没写几点：不发请求，就地说明', async () => {
    const calls: Call[] = [];
    open('/gig', { 'GET /gig/available': OFF, 'GET /gig/places': places }, calls);
    fireEvent.change(await screen.findByLabelText('终点'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('什么时候出发'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: '看看顺路的单' }));
    expect(await screen.findByText(DEPART_HINT)).toBeTruthy();
    expect(calls.some((c) => c.path === '/gig/along')).toBe(false);
  });
});
