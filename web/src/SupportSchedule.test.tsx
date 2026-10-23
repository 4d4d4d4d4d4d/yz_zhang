// ESCA-068（260 号 spec）后台工单台「我的排班」：勾周几、填几点到几点保存；显示现在在不在排班里；能取消；主管看板标「不在排班里」。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ADMIN = { id: 1, phone: '138****0001', nickname: '客服甲', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['support'], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r1' };
const ROW = { id: 7, user_id: 9, subject: '钱没到账', body: '', created_at: '2026-10-13T00:00:00Z', assignee_id: null,
  assignee_nickname: '', escalation_level: 0, escalation_label: '', waited_hours: 1, sla_hours: 4, overdue_hours: 0,
  first_responded: false, first_response_hours: 1, first_response_overdue: false, replies_count: 0,
  last_user_reply: '', last_user_reply_at: null, awaiting_staff: false, category: 'funds', priority: 'urgent', priority_label: '加急' };
const LABELS = { funds: '资金（提现、退款、到账）', account: '账号（登录、安全）', general: '一般' };
type Call = { method: string; url: string; body?: unknown };

function open(scope: unknown, calls: Call[], me: unknown = ADMIN, agents: unknown = []) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    const sent = init?.body ? JSON.parse(init.body) : undefined;
    calls.push({ method, url: p, body: sent });
    const body = p === '/users/me' ? me : p === '/admin/tickets' ? [ROW]
      : p === '/admin/support/my-categories' ? scope
      : p === '/admin/support/my-schedule' ? { schedule: sent.windows, on_duty: false }
      : p === '/admin/support/agents' ? agents
      : p === '/admin/admins' ? { admins: [] }
      : p === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('ESCA-068 排班', () => {
  it('ESCA-069 同一天加第二段（早晚两班）；改排班时带出已有的', async () => {
    const calls: Call[] = [];
    open({ categories: ['funds'], declared: true, labels: LABELS, auto_assign: true, on_duty: true,
      schedule: [{ weekday: 5, start: '09:00', end: '12:00' }] }, calls);
    const box = await screen.findByLabelText('我的排班');
    fireEvent.click(within(box).getByText('改排班'));
    expect((within(box).getByLabelText('第 1 段周几') as HTMLSelectElement).value).toBe('5');
    expect((within(box).getByLabelText('第 1 段开始') as HTMLInputElement).value).toBe('09:00');
    fireEvent.click(within(box).getByText('加一段'));
    expect((within(box).getByLabelText('第 2 段周几') as HTMLSelectElement).value).toBe('5');
    fireEvent.change(within(box).getByLabelText('第 2 段周几'), { target: { value: '6' } });
    fireEvent.click(within(box).getByText('保存排班'));
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT' && c.url === '/admin/support/my-schedule')?.body).toEqual(
      { windows: [{ weekday: 5, start: '09:00', end: '12:00' }, { weekday: 6, start: '19:00', end: '22:00' }] }));
    fireEvent.click(await within(box).findByText('改排班'));
    fireEvent.click(within(box).getByText('工作日 9–18'));
    expect(within(box).getByTestId('schedule-row-4')).toBeTruthy();
    expect(within(box).queryByTestId('schedule-row-5')).toBeNull();
  });

  it('ESCA-071 把周一的早晚两班复制到周二、周三：目标那天原有的被替换', async () => {
    const calls: Call[] = [];
    open({ categories: ['funds'], declared: true, labels: LABELS, auto_assign: true, on_duty: true,
      schedule: [{ weekday: 0, start: '08:00', end: '12:00' }, { weekday: 0, start: '18:00', end: '22:00' }, { weekday: 2, start: '09:00', end: '18:00' }] }, calls);
    const box = await screen.findByLabelText('我的排班');
    fireEvent.click(within(box).getByText('改排班'));
    const copy = within(box).getByLabelText('复制排班');
    expect(within(copy).getByText('复制')).toHaveProperty('disabled', true);
    fireEvent.click(within(copy).getByLabelText('复制到周二'));
    fireEvent.click(within(copy).getByLabelText('复制到周三'));
    fireEvent.click(within(copy).getByText('复制'));
    fireEvent.click(within(box).getByText('保存排班'));
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT' && c.url === '/admin/support/my-schedule')?.body).toEqual({ windows: [
      { weekday: 0, start: '08:00', end: '12:00' }, { weekday: 0, start: '18:00', end: '22:00' },
      { weekday: 1, start: '08:00', end: '12:00' }, { weekday: 1, start: '18:00', end: '22:00' },
      { weekday: 2, start: '08:00', end: '12:00' }, { weekday: 2, start: '18:00', end: '22:00' }] }));
  });

  it('勾周几、填时间保存：发出每天一段，显示排班与「现在不在排班里」；能取消', async () => {
    const calls: Call[] = [];
    open({ categories: ['funds'], declared: true, labels: LABELS, auto_assign: true }, calls);
    const box = await screen.findByLabelText('我的排班');
    expect(box.textContent).toContain('没设排班');
    fireEvent.click(within(box).getByText('设排班'));
    // 默认填好工作日 9–18 五段：删掉后三段，前两段改成 10:00–19:30
    for (let k = 0; k < 3; k++) fireEvent.click(within(within(box).getByTestId('schedule-row-2')).getByText('删掉这段'));
    expect(within(box).queryByTestId('schedule-row-2')).toBeNull();
    for (const i of [1, 2]) {
      fireEvent.change(within(box).getByLabelText(`第 ${i} 段开始`), { target: { value: '10:00' } });
      fireEvent.change(within(box).getByLabelText(`第 ${i} 段结束`), { target: { value: '19:30' } });
    }
    fireEvent.click(within(box).getByText('保存排班'));
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT' && c.url === '/admin/support/my-schedule')?.body).toEqual(
      { windows: [{ weekday: 0, start: '10:00', end: '19:30' }, { weekday: 1, start: '10:00', end: '19:30' }] }));
    expect((await within(box).findByTestId('my-schedule')).textContent).toContain('周一 10:00–19:30、周二 10:00–19:30');
    expect(within(box).getByTestId('my-schedule').textContent).toContain('现在不在排班里');
    expect(within(box).getByRole('status').textContent).toContain('到点自动恢复');
    fireEvent.click(within(box).getByText('取消排班'));
    await waitFor(() => expect(calls.filter((c) => c.url === '/admin/support/my-schedule').slice(-1)[0]?.body).toEqual({ windows: [] }));
    await waitFor(() => expect(box.textContent).toContain('没设排班'));
  });

  it('主管看板：没暂停但不在排班里的写「不在排班里」并列出排班', async () => {
    const boss = { ...ADMIN, admin_roles: ['super'] };
    const agents = [
      { user_id: 2, nickname: '乙', categories: ['funds'], declared: true, auto_assign: true, paused_until: null, open_tickets: 0,
        on_duty: false, schedule: [{ weekday: 5, start: '09:00', end: '18:00' }] },
      { user_id: 3, nickname: '丙', categories: [], declared: false, auto_assign: false, paused_until: null, open_tickets: 1,
        on_duty: true, schedule: [] },
    ];
    open({ categories: [], declared: false, labels: LABELS }, [], boss, agents);
    fireEvent.click(await screen.findByText('看客服状态'));
    const b = await screen.findByTestId('agent-2');
    expect(b.textContent).toContain('不在排班里');
    expect(b.textContent).toContain('周六 09:00–18:00');
    expect((await screen.findByTestId('agent-3')).textContent).toContain('在岗');
  });
});
