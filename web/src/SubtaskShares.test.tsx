// AI-DEC-024（321 号 spec）项目里的一步：交付人把成果开放给下一步、随时收回；下一步的执行者看前一步开放的成果。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = (id: number) => ({ id, phone: '138****0002', nickname: 'x', bio: '', city: '上海', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r' });
const TASK = (id: number, status: string, executor: number) => ({ id, title: id === 11 ? '需求文档' : '前端开发', description: '', category: '软件开发',
  status, budget_cents: 5000, creator_id: 9, executor_id: executor, is_remote: true, city: '', address_hint: '', address_exact: '', parent_id: 10,
  task_type: 'project', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none', depends_on: id === 12 ? [11] : [] });
const VIEW = (shared: boolean, delivered = true) => ({ task_id: 11, delivered,
  next_steps: [{ task_id: 12, title: '前端开发', status: 'in_progress', executor_nickname: '小李', shared, ...(shared ? { share_id: 5 } : {}) }] });
const INPUTS = [{ from_task_id: 11, title: '需求文档', shared_at: '2030-01-05T02:00:00Z',
  deliveries: [{ content: '接口约定见第 3 页', images: [], created_at: '2030-01-05T01:00:00Z' }], previews: [{ id: 3, url: '/api/v1/files/p.png' }] }];
type Call = { method: string; path: string; body?: unknown };

function open(me: number, taskId: number, task: unknown, calls: Call[], routes: Record<string, unknown>) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const body = p === '/users/me' ? ME(me) : p === `/tasks/${taskId}` ? task : routes[`${method} ${p}`] ?? [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={[`/tasks/${taskId}`]}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('AI-DEC-024 跨子任务产出共享', () => {
  it('交付人：交了之后开放给下一步、再收回', async () => {
    const calls: Call[] = [];
    open(2, 11, TASK(11, 'pending_acceptance', 2), calls, {
      'GET /tasks/11/shares': VIEW(false), 'POST /tasks/11/shares': VIEW(true), 'DELETE /tasks/11/shares/5': VIEW(false) });
    const box = await screen.findByLabelText('开放给下一步');
    expect(within(box).getByText(/小李/)).toBeTruthy();
    fireEvent.click(await within(box).findByText('开放给这一步'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks/11/shares')?.body).toEqual({ to_task_id: 12 }));
    expect(await within(box).findByText('已开放')).toBeTruthy();
    fireEvent.click(within(box).getByText('收回'));
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.path === '/tasks/11/shares/5')).toBe(true));
    expect(await within(box).findByText('开放给这一步')).toBeTruthy();
  });

  it('还没交付：只说明交了之后能开，没有按钮', async () => {
    open(2, 11, TASK(11, 'in_progress', 2), [], { 'GET /tasks/11/shares': VIEW(false, false) });
    const box = await screen.findByLabelText('开放给下一步');
    expect(within(box).getByText(/交付之后，可以把交付说明和预览图开放/)).toBeTruthy();
    expect(within(box).queryByText('开放给这一步')).toBeNull();
  });

  it('下一步的执行者：看得到前一步开放的交付说明与预览图；没开放就没有这一块', async () => {
    open(3, 12, TASK(12, 'in_progress', 3), [], { 'GET /tasks/12/inputs': INPUTS });
    const box = await screen.findByLabelText('前一步的成果');
    expect(within(box).getByText('接口约定见第 3 页')).toBeTruthy();
    expect(within(box).getByAltText('前一步的预览图').getAttribute('src')).toBe('/api/v1/files/p.png');
  });

  it('前一步没开放：不出「前一步的成果」', async () => {
    open(3, 12, TASK(12, 'in_progress', 3), [], {});
    expect(await screen.findByText('前端开发')).toBeTruthy();
    expect(screen.queryByLabelText('前一步的成果')).toBeNull();
  });
});
