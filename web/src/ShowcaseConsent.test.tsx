// SCN-156（278 号 spec）作品展示授权：已完成的单发单人在任务详情里允许 / 撤回；接单人在空间编辑里填关联的任务编号。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 2, phone: '138****0002', nickname: '我', bio: '', city: '上海', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2' };
type Call = { method: string; path: string; body?: unknown };
const TASK = (extra: Record<string, unknown>) => ({ id: 60, title: '衣橱整理', description: '', category: '整理收纳', status: 'completed', budget_cents: 20000,
  creator_id: 2, executor_id: 3, is_remote: false, city: '上海', address_hint: '', address_exact: '', parent_id: null,
  task_type: 'service', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none', ...extra });
const SPACE = { user_id: 2, nickname: '我', headline: '整理收纳', theme: 'clay', kind: 'person', items_count: 1, accepting_orders: false,
  introduction: '', items: [{ title: '衣橱整理前后', kind: 'work', summary: '', url: '' }], revision: 3, published: true, profile_public: true };

function open(path: string, calls: Call[], routes: Record<string, unknown>) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const key = `${method} ${p}`;
    const body = key in routes ? routes[key] : p in routes ? routes[p] : p === '/users/me' ? ME : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={[path]}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('SCN-156 作品展示授权', () => {
  it('已完成的单：发单人点「允许展示这一单」', async () => {
    const calls: Call[] = [];
    open('/tasks/60', calls, { '/tasks/60': TASK({}), 'POST /tasks/60/showcase-consent': { task_id: 60, showcase_consent_at: '2026-10-23T00:00:00Z' } });
    const box = await screen.findByLabelText('作品展示授权');
    expect(box.textContent).toContain('要你同意');
    fireEvent.click(screen.getByText('允许展示这一单'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/tasks/60/showcase-consent')).toBe(true));
  });

  it('已授权时显示「撤回展示授权」；不是发单人看不到', async () => {
    const calls: Call[] = [];
    open('/tasks/60', calls, { '/tasks/60': TASK({ showcase_consent_at: '2026-10-23T00:00:00Z' }) });
    fireEvent.click(await screen.findByText('撤回展示授权'));
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.path === '/tasks/60/showcase-consent')).toBe(true));
  });

  it('不是发单人：没有这一块', async () => {
    open('/tasks/60', [], { '/tasks/60': TASK({ creator_id: 9, executor_id: 2 }) });
    await screen.findByText('衣橱整理');
    expect(screen.queryByLabelText('作品展示授权')).toBeNull();
  });

  it('空间编辑：填任务编号带进保存的请求；不填不带', async () => {
    const calls: Call[] = [];
    open('/space/edit', calls, { 'GET /spaces/me': SPACE, 'PUT /spaces/me': { ...SPACE, revision: 4 } });
    fireEvent.change(await screen.findByLabelText('内容 1 关联任务'), { target: { value: '60' } });
    fireEvent.submit(screen.getByLabelText('内容 1 关联任务').closest('form')!);
    await waitFor(() => expect((calls.find((c) => c.method === 'PUT' && c.path === '/spaces/me')?.body as { items: unknown[] }).items)
      .toEqual([{ title: '衣橱整理前后', kind: 'work', summary: '', url: '', task_id: 60 }]));
  });
});
