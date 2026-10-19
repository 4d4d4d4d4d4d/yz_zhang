// ESCA-057（227 号 spec）工单里附截图：提单与补充都能附，附了才带 images；工单与后台往来里看得到。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

// jsdom 没有 createImageBitmap：选图组件换成一个直接给出 url 的替身，这里测的是工单怎么带图
vi.mock('./PhotoPicker', () => ({
  default: ({ urls, onChange }: { urls: string[]; onChange: (u: string[]) => void }) => (
    <button onClick={() => onChange([...urls, `/api/v1/files/shot${urls.length + 1}abcdef`])}>替身加图（{urls.length}）</button>
  ),
}));

const ME = { id: 9, phone: '138****0009', nickname: '我', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, admin_roles: [], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r9' };
const T = { id: 3, subject: '提现页面报错', body: '见截图', status: 'open', reply: '', created_at: '2026-10-13T00:00:00Z',
  claimed: false, escalation_level: 0, escalation_label: '', waited_hours: 1, sla_hours: 24, overdue_hours: 0,
  first_responded: false, first_response_hours: 4, first_response_overdue: false, category: 'general', priority: 'normal', priority_label: '一般',
  images: ['/api/v1/files/aaaa1111'], replies: [{ body: '又一张', is_staff: false, created_at: '2026-10-13T01:00:00Z', images: ['/api/v1/files/bbbb2222'] }] };
type Call = { method: string; path: string; body?: unknown };

function open(path: string, me: unknown, routes: Record<string, unknown>, calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const key = Object.keys(routes).find((k) => k === `${method} ${p}`) ?? Object.keys(routes).find((k) => k === p);
    const body = p === '/users/me' ? me : key ? routes[key] : p === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={[path]}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('ESCA-057 工单截图', () => {
  it('提单带上截图；没附图时请求体与以前一样；工单里显示截图', async () => {
    const calls: Call[] = [];
    open('/support', ME, { 'GET /support/tickets': [T], 'POST /support/tickets': { id: 4, status: 'open', reply: '' },
      'POST /support/tickets/3/replies': { ...T, reopened: false } }, calls);
    expect(await screen.findByTestId('ticket-images-3')).toBeTruthy();
    expect(screen.getByTestId('ticket-reply-images-3-0').querySelectorAll('img')).toHaveLength(1);
    fireEvent.change(screen.getByPlaceholderText('问题一句话概括'), { target: { value: '提现页面报错' } });
    fireEvent.click(screen.getAllByText(/替身加图/)[0]);
    fireEvent.click(screen.getByRole('button', { name: '提交工单' }));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/support/tickets')?.body)
      .toEqual({ subject: '提现页面报错', body: '', images: ['/api/v1/files/shot1abcdef'] }));
    // 补充：附了图才带 images
    fireEvent.change(screen.getByLabelText('补充工单 3'), { target: { value: '再补一张' } });
    fireEvent.click(screen.getAllByText(/替身加图/)[1]);
    fireEvent.click(screen.getByRole('button', { name: '补充' }));
    await waitFor(() => expect(calls.find((c) => c.path === '/support/tickets/3/replies')?.body)
      .toEqual({ body: '再补一张', images: ['/api/v1/files/shot1abcdef'] }));
  });

  it('后台看完整往来时截图也在', async () => {
    const ADMIN = { ...ME, id: 1, is_admin: true, admin_roles: ['support'] };
    const ROW = { id: 7, user_id: 9, subject: '提现页面报错', body: '见截图', created_at: '2026-10-13T00:00:00Z', assignee_id: 1,
      assignee_nickname: '客服甲', escalation_level: 0, escalation_label: '', waited_hours: 5, sla_hours: 24, overdue_hours: 0,
      first_responded: true, first_response_hours: 4, first_response_overdue: false, replies_count: 1,
      last_user_reply: '', last_user_reply_at: null, awaiting_staff: false, category: 'general', priority: 'normal', priority_label: '一般' };
    const DETAIL = { ...ROW, user_nickname: '小林', status: 'open', reply: '', resolved_at: null, images: ['/api/v1/files/aaaa1111'],
      thread: [{ body: '补一张', is_staff: false, author: '提单人', created_at: '2026-10-14T00:00:00Z', images: ['/api/v1/files/bbbb2222'] }] };
    open('/admin', ADMIN, { '/admin/tickets': [ROW], '/admin/tickets/7': DETAIL }, []);
    fireEvent.click(await screen.findByRole('button', { name: '看完整往来' }));
    expect((await screen.findByTestId('admin-ticket-images-7')).querySelector('img')?.getAttribute('src')).toBe('/api/v1/files/aaaa1111');
    expect(screen.getByTestId('admin-thread-images-7-0').querySelector('img')?.getAttribute('src')).toBe('/api/v1/files/bbbb2222');
  });
});
