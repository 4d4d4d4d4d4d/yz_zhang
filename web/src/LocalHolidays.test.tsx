// ESCA-073（305 号 spec）后台客服看板：主管给客服设地区；节假日日历下多「地区性假日」，没人设这个地区时提醒不起作用。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const BOSS = { id: 1, phone: '138****0001', nickname: '主管', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['super'], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r1' };
const ROW = { id: 7, user_id: 9, subject: '钱没到账', body: '', created_at: '2026-10-13T00:00:00Z', assignee_id: null,
  assignee_nickname: '', escalation_level: 0, escalation_label: '', waited_hours: 1, sla_hours: 4, overdue_hours: 0,
  first_responded: false, first_response_hours: 1, first_response_overdue: false, replies_count: 0,
  last_user_reply: '', last_user_reply_at: null, awaiting_staff: false, category: 'funds', priority: 'urgent', priority_label: '加急' };
const LABELS = { funds: '资金（提现、退款、到账）', account: '账号（登录、安全）', general: '一般' };
const AGENTS = [
  { user_id: 2, nickname: '乙', categories: [], declared: false, auto_assign: false, paused_until: null, open_tickets: 0,
    on_duty: false, schedule: [], region: '新疆' },
  { user_id: 3, nickname: '丙', categories: [], declared: false, auto_assign: false, paused_until: null, open_tickets: 0,
    on_duty: true, schedule: [] },
];
const LOCAL = [{ id: 5, day: '2027-05-16', region: '新疆', label: '古尔邦节', agents: 1 },
  { id: 6, day: '2027-05-16', region: '宁夏', label: '古尔邦节', agents: 0 }];
type Call = { method: string; url: string; body?: unknown };

function open(calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    const sent = init?.body ? JSON.parse(init.body) : undefined;
    calls.push({ method, url: p, body: sent });
    const body = p === '/users/me' ? BOSS : p === '/admin/tickets' ? [ROW]
      : p === '/admin/support/my-categories' ? { categories: [], declared: false, labels: LABELS }
      : p === '/admin/support/agents' ? AGENTS
      : p === '/admin/support/local-holidays' && method === 'GET' ? LOCAL
      : p === '/admin/support/local-holidays' ? { id: 7, ...sent, agents: 0 }
      : p.endsWith('/region') ? { user_id: 3, region: sent.region || null }
      : p === '/admin/admins' ? { admins: [] }
      : p === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('ESCA-073 地区性假日', () => {
  it('看板上看得到地区，能给客服设地区', async () => {
    const calls: Call[] = [];
    open(calls);
    fireEvent.click(await screen.findByText('看客服状态'));
    expect((await screen.findByTestId('agent-2')).textContent).toContain('新疆');
    const c = screen.getByTestId('agent-3');
    expect(c.textContent).toContain('不分地区');
    const ask = vi.spyOn(window, 'prompt').mockReturnValue(' 宁夏 ');
    try {
      fireEvent.click(within(c).getByText('设地区'));
      await waitFor(() => expect(calls.find((x) => x.method === 'PUT' && x.url === '/admin/support/agents/3/region')?.body)
        .toEqual({ region: '宁夏' }));
      expect(await screen.findByText('已把 丙 设为「宁夏」：当地放假那天他不在岗')).toBeTruthy();
    } finally { ask.mockRestore(); }
  });

  it('地区性假日：列出影响几位、没人设这个地区时说不起作用；能录入、删掉', async () => {
    const calls: Call[] = [];
    open(calls);
    fireEvent.click(await screen.findByText('看客服状态'));
    const box = await screen.findByLabelText('地区性假日');
    expect((await within(box).findByTestId('local-holiday-5')).textContent).toContain('2027-05-16 新疆 放假 古尔邦节 · 影响 1 位客服');
    expect(within(box).getByTestId('local-holiday-6').textContent).toContain('还没有客服设为「宁夏」，这一天不起作用');
    const add = within(box).getByText('录入地区假日') as HTMLButtonElement;
    fireEvent.change(within(box).getByLabelText('地区假日日期'), { target: { value: '2027-03-20' } });
    expect(add.disabled).toBe(true);
    fireEvent.change(within(box).getByLabelText('地区'), { target: { value: ' 新疆 ' } });
    fireEvent.change(within(box).getByLabelText('地区假日说明'), { target: { value: '肉孜节' } });
    fireEvent.click(add);
    await waitFor(() => expect(calls.find((x) => x.method === 'POST' && x.url === '/admin/support/local-holidays')?.body)
      .toEqual({ day: '2027-03-20', region: '新疆', label: '肉孜节' }));
    fireEvent.click(within(within(box).getByTestId('local-holiday-5')).getByText('删掉'));
    await waitFor(() => expect(calls.some((x) => x.method === 'DELETE' && x.url === '/admin/support/local-holidays/5')).toBe(true));
  });
});
