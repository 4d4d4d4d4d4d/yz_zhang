// VER-050（372 号 spec）：发单人点名核验人——填了编号就带上，空着就由平台派单，乱填说清楚；核验台写清这一单是点名来的。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 1, phone: '138****0000', nickname: '发布方', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0 };
const TASK = { id: 7, title: '写一篇接口文档', description: '', category: '软件开发', status: 'in_progress', budget_cents: 20000,
  creator_id: 1, executor_id: 9, is_remote: true, city: '', address_hint: '', address_exact: '', parent_id: null, task_type: 'simple',
  pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none' };
type Call = { method: string; path: string; body: unknown };

function open(path: string, extra: Record<string, unknown> = {}) {
  localStorage.setItem('token', 'tok');
  const calls: Call[] = [];
  const routes: Record<string, unknown> = {
    '/users/me': ME, '/tasks/7': TASK,
    '/agents': [{ user_id: 9, name: '开发助理', domains: ['软件开发'], max_task_budget_cents: 50000, runs_total: 1, runs_succeeded: 0, is_active: true }],
    '/tasks/7/agent-runs': { runs: [{ id: 1, task_id: 7, status: 'escalated', confidence_bps: 4000, output: '半成品', criteria_results: [],
      error: '', moderation_status: 'pass', created_at: null, finished_at: null }], delivery_block: 'AI 置信度不足，需人工核验后方可提交交付' },
    'POST /tasks/7/verification': { id: 3, task_id: 7, status: 'open', trigger: 'designated', fee_cents: 3000, payer_id: 1, verifier_id: null,
      designated_verifier_id: 42, outcome: '', comment: '', revised_output: '', criteria_results: [], deadline: null, created_at: null },
    ...extra,
  };
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const hit = routes[`${method} ${p}`] ?? routes[p];
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ?? []) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={[path]}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
  return calls;
}

const posts = (calls: Call[]) => calls.filter((c) => c.method === 'POST' && c.path === '/tasks/7/verification');

describe('VER-050 网页：点名核验人', () => {
  it('填了编号：带 verifier_id，并说清已通知对方', async () => {
    const calls = open('/tasks/7');
    await screen.findByTestId('delivery-block');
    expect(screen.getByText(/核验费由你付/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText('点名核验人的用户编号'), { target: { value: '42' } });
    fireEvent.click(screen.getByText('申请人工核验'));
    await waitFor(() => expect(posts(calls).length).toBe(1));
    expect(posts(calls)[0].body).toEqual({ verifier_id: 42 });
    expect(await screen.findByText('核验单已提交，已通知你点名的核验人')).toBeTruthy();
  });

  it('空着：和原来一样不带请求体；乱填：不发请求，说清怎么填', async () => {
    const calls = open('/tasks/7');
    await screen.findByTestId('delivery-block');
    fireEvent.change(screen.getByLabelText('点名核验人的用户编号'), { target: { value: '老周' } });
    fireEvent.click(screen.getByText('申请人工核验'));
    expect(await screen.findByText('用户编号填正整数；不点名就空着')).toBeTruthy();
    expect(posts(calls).length).toBe(0);
    fireEvent.change(screen.getByLabelText('点名核验人的用户编号'), { target: { value: '' } });
    fireEvent.click(screen.getByText('申请人工核验'));
    await waitFor(() => expect(posts(calls).length).toBe(1));
    expect(posts(calls)[0].body).toBeUndefined();
  });

  it('核验台：点名来的单写清「发布方点名请你核验（发布方付费）」', async () => {
    open('/verify', { '/verification-orders': [{ id: 3, task_id: 7, status: 'open', trigger: 'designated', fee_cents: 3000, payer_id: 1,
      verifier_id: null, designated_verifier_id: 1, outcome: '', comment: '', revised_output: '', criteria_results: [], deadline: null,
      created_at: null, category: '软件开发', task_title: '写一篇接口文档', claimable: true, reason: '' }] });
    expect(await screen.findByText('发布方点名请你核验（发布方付费）')).toBeTruthy();
  });
});

describe('VER-050b 网页：被点名的核验人当场拒绝（374 号 spec）', () => {
  const order = (designated: number | null) => ({ id: 3, task_id: 7, status: 'open', trigger: designated ? 'designated' : 'requested', fee_cents: 3000,
    payer_id: 5, verifier_id: null, designated_verifier_id: designated, outcome: '', comment: '', revised_output: '', criteria_results: [],
    deadline: null, created_at: null, category: '软件开发', task_title: '写一篇接口文档', claimable: true, reason: '' });

  it('点名我的单：能拒绝，理由带上去，并说清钱已退回', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue('这周出差');
    const calls = open('/verify', { '/verification-orders': [order(1)], 'POST /verification-orders/3/decline': { ...order(1), status: 'cancelled' } });
    fireEvent.click(await screen.findByText('不方便，拒绝'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/verification-orders/3/decline')).toBe(true));
    expect(calls.find((c) => c.path === '/verification-orders/3/decline')!.body).toEqual({ reason: '这周出差' });
    expect(await screen.findByText('已拒绝，核验费已退回给发布方')).toBeTruthy();
  });

  it('平台派的单、点名别人的单：没有拒绝按钮', async () => {
    open('/verify', { '/verification-orders': [order(null), { ...order(9), id: 4 }] });
    await screen.findAllByText('写一篇接口文档');
    expect(screen.queryByText('不方便，拒绝')).toBeNull();
  });
});
