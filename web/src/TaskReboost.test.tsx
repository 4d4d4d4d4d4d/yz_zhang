// AI-DEC-023（320 号 spec）没人报名的单：发单人一键再推一次，可选加价；有人报名、一单多天的母任务不给。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 9, phone: '138****0009', nickname: 'x', bio: '', city: '上海', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r' };
const TASK = { id: 80, title: '上门开锁', description: '', category: '上门开锁', status: 'published', budget_cents: 10000,
  creator_id: 9, executor_id: null, is_remote: false, city: '上海', address_hint: '', address_exact: '', parent_id: null,
  task_type: 'service', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none', days: 1 };
const APP_ROW = { id: 3, task_id: 80, applicant_id: 2, nickname: '小王', credit_score: 100, rating_avg: 5, message: '能来', bid_cents: 10000, status: 'pending' };
type Call = { method: string; path: string; body?: unknown };

function open(calls: Call[], task: unknown = TASK, apps: unknown[] = []) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const body = p === '/users/me' ? ME : p === '/tasks/80' ? task : p === '/tasks/80/applications' ? apps
      : p === '/tasks/80/reboost' ? { task_id: 80, raise_cents: 2000, budget_cents: 12000 } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/tasks/80']}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('AI-DEC-023 再推一次', () => {
  it('没人报名：加价写错不发；写对了带上分数并说清结果', async () => {
    const calls: Call[] = [];
    open(calls);
    const box = await screen.findByLabelText('再推一次');
    fireEvent.change(within(box).getByLabelText('加价（元）'), { target: { value: '-5' } });
    fireEvent.click(within(box).getByText('再推一次'));
    expect(await within(box).findByText(/加价写一个正数/)).toBeTruthy();
    expect(calls.some((c) => c.path === '/tasks/80/reboost')).toBe(false);
    fireEvent.change(within(box).getByLabelText('加价（元）'), { target: { value: '20' } });
    fireEvent.click(within(box).getByText('再推一次'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks/80/reboost')?.body).toEqual({ raise_cents: 2000 }));
    expect(await within(box).findByText(/已再推一次，加价 ¥20.00（现在预算 ¥120.00）/)).toBeTruthy();
  });

  it('有人报名就不出「再推一次」', async () => {
    open([], TASK, [APP_ROW]);
    expect(await screen.findByText(/小王/)).toBeTruthy();
    expect(screen.queryByLabelText('再推一次')).toBeNull();
  });

  it('一单多天的母任务不出（走按天补招）', async () => {
    open([], { ...TASK, days: 3 });
    expect(await screen.findByText('暂无报名')).toBeTruthy();
    expect(screen.queryByLabelText('再推一次')).toBeNull();
  });
});
