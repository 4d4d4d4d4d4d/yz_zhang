// AI-DEC-021d（386 号 spec）：接单人更新进度时报「还要几天」；发单人看得到，自己不能替他报。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const user = (id: number) => ({
  id, phone: '138****0002', nickname: id === 5 ? '陈设计' : '我', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100,
  rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r',
});
const TASK = { id: 21, title: '公司官网 - 页面开发', description: '', category: '软件开发', status: 'in_progress', budget_cents: 300000,
  creator_id: 2, executor_id: 5, is_remote: true, city: '', address_hint: '', address_exact: '', parent_id: null,
  task_type: 'project', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none' };
const LOGS = [
  { id: 1, user_id: 5, kind: 'note', content: '首页做完', images: [], created_at: '2026-11-04T08:00:00Z', days_left: 4 },
  { id: 2, user_id: 5, kind: 'note', content: '联调中', images: [], created_at: '2026-11-04T09:00:00Z', days_left: 0 },
  { id: 3, user_id: 2, kind: 'note', content: '辛苦', images: [], created_at: '2026-11-04T10:00:00Z' },
];

function open(meId: number) {
  localStorage.setItem('token', 'tok');
  const calls: Array<{ method: string; path: string; body: unknown }> = [];
  const routes: Record<string, unknown> = { '/users/me': user(meId), '/tasks/21': TASK, '/tasks/21/progress': LOGS };
  const fetchImpl = vi.fn(async (url: string, init?: RequestInit) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path: p, body: init?.body ? JSON.parse(String(init.body)) : null });
    return { ok: true, status: 200, text: async () => JSON.stringify(init?.method === 'POST' ? { ok: true } : routes[p] ?? []) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/tasks/21']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
  return calls;
}

describe('AI-DEC-021d 进度里的「还要几天」（386 号 spec）', () => {
  it('执行动态写出接单人报的天数', async () => {
    open(2);
    expect(await screen.findByText(/首页做完（还要 4 天）/)).toBeTruthy();
    expect(screen.getByText(/联调中（今天做完）/)).toBeTruthy();
    expect(screen.getByText(/^\[note\] 辛苦 ·/)).toBeTruthy();
  });

  it('发单人的进度表单没有「还要几天」', async () => {
    open(2);
    await screen.findByText('更新进度');
    expect(screen.queryByLabelText('还要几天')).toBeNull();
  });

  it('接单人填了才带上；填得不对不让提交', async () => {
    const calls = open(5);
    const input = await screen.findByLabelText('还要几天');
    fireEvent.change(screen.getByPlaceholderText('进度说明…'), { target: { value: '接口联调' } });
    fireEvent.change(input, { target: { value: '1.5' } });
    expect((screen.getByText('更新进度') as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('还要几天填 0~365 的整数（0 = 今天做完）')).toBeTruthy();
    fireEvent.change(input, { target: { value: '3' } });
    fireEvent.click(screen.getByText('更新进度'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/tasks/21/progress')).toBe(true));
    expect(calls.find((c) => c.method === 'POST')!.body).toEqual({ content: '接口联调', images: [], days_left: 3 });
    await waitFor(() => expect((input as HTMLInputElement).value).toBe(''));
    // 不填：不带这个字段
    fireEvent.change(screen.getByPlaceholderText('进度说明…'), { target: { value: '传了截图' } });
    fireEvent.click(screen.getByText('更新进度'));
    await waitFor(() => expect(calls.filter((c) => c.method === 'POST')).toHaveLength(2));
    expect(calls.filter((c) => c.method === 'POST')[1].body).toEqual({ content: '传了截图', images: [] });
  });
});
