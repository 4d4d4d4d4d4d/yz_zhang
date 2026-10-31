// SCN-110 任务详情上的创作类需求九项（194 号 spec）：接单的人看到「报名前可以先问问发单人」，发单人自己看到「还可以补」。
import { PlatformClient } from '@platform/core';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { TaskProfilePanel } from './Profiles';
import { AppProvider } from './store';

const ME = (id: number) => ({ id, phone: '138', nickname: '我', bio: '', city: '上海', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r' });
const TASK = { id: 71, title: '咖啡店海报', description: '要一张海报', category: '设计', status: 'published', budget_cents: 50000,
  creator_id: 9, executor_id: null, is_remote: true, city: '上海', address_hint: '', address_exact: '', parent_id: null,
  task_type: 'service', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none' };
const BRIEF = { missing: 2, items: [
  { name: '用途', ok: true, ask: '这个东西用在哪儿？' },
  { name: '改稿次数', ok: false, ask: '包含几次修改？超出的怎么算（建议走变更单）？' },
  { name: '版权授权', ok: false, ask: '版权怎么约定？' }] };
const PROFILE = { task_id: 71, category: '设计', mode: 'remote', declared_skills: [], inferred_skills: [], size: 'medium',
  price: { sample_size: 0, p50_cents: null, min_cents: null, max_cents: null, position: 'unknown' }, risks: [], completeness: 0.6, checks: [] };

function open(meId: number, brief: unknown) {
  localStorage.setItem('token', 'tok');
  const routes: Record<string, unknown> = { '/users/me': ME(meId), '/tasks/71': TASK, '/tasks/71/profile': { ...PROFILE, brief } };
  const fetchImpl = vi.fn(async (url: string) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    return { ok: true, status: 200, text: async () => JSON.stringify(routes[p] ?? []) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/tasks/71']}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('SCN-110 任务详情上的需求九项', () => {
  it('接单的人：没写的几项写成报名前该问的话', async () => {
    open(2, BRIEF);
    const box = await screen.findByLabelText('需求九项');
    expect(box.textContent).toContain('说明里没写的 2 项，报名前可以先问问发单人：');
    expect(box.textContent).toContain('改稿次数：包含几次修改？');
    expect(box.textContent).toContain('版权授权：版权怎么约定？');
    expect(box.textContent).not.toContain('用途');
  });

  it('发单人自己：写成还可以补什么', async () => {
    open(9, BRIEF);
    const box = await screen.findByLabelText('需求九项');
    expect(box.textContent).toContain('创作类需求一般写清九项，已写 1/3。还可以补：');
  });

  it('不是创作类、或九项都写了：不显示', async () => {
    open(2, null);
    await screen.findByLabelText('任务画像');
    expect(screen.queryByLabelText('需求九项')).toBeNull();
  });
});

describe('SCN-135 带着这些问题报名', () => {
  function openWithCalls(meId: number, task: unknown, calls: Array<{ method: string; path: string; body?: unknown }>) {
    localStorage.setItem('token', 'tok');
    const routes: Record<string, unknown> = { '/users/me': ME(meId), '/tasks/71': task, '/tasks/71/profile': { ...PROFILE, brief: BRIEF },
      '/tasks/71/applications': { id: 5, status: 'pending' } };
    const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
      const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
      calls.push({ method: init?.method ?? 'GET', path: p, body: init?.body ? JSON.parse(init.body) : undefined });
      return { ok: true, status: 200, text: async () => JSON.stringify(routes[p] ?? []) };
    }) as unknown as typeof fetch;
    render(<MemoryRouter initialEntries={['/tasks/71']}>
      <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
  }

  it('接单的人一键报名，留言里写着没写的几项', async () => {
    const calls: Array<{ method: string; path: string; body?: unknown }> = [];
    openWithCalls(2, TASK, calls);
    fireEvent.click(await screen.findByRole('button', { name: '带着这些问题报名' }));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks/71/applications')?.body).toEqual({
      message: '我可以做。报名前想先确认几件事：\n1. 改稿次数：包含几次修改？超出的怎么算（建议走变更单）？\n2. 版权授权：版权怎么约定？' }));
  });

  it('发单人自己、或单已不在招：没有这个按钮', async () => {
    openWithCalls(9, TASK, []);
    await screen.findByLabelText('需求九项');
    expect(screen.queryByRole('button', { name: '带着这些问题报名' })).toBeNull();
    cleanup();
    openWithCalls(2, { ...TASK, status: 'in_progress' }, []);
    await screen.findByLabelText('需求九项');
    expect(screen.queryByRole('button', { name: '带着这些问题报名' })).toBeNull();
  });
});

describe('SCN-135 画像面板自己也守住：发单人看不到报名按钮', () => {
  it('就算传了回调，发单人那一侧也不给按钮', async () => {
    const fetchImpl = vi.fn(async (url: string) => {
      const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
      return { ok: true, status: 200, text: async () => JSON.stringify(p === '/tasks/71/profile' ? { ...PROFILE, brief: BRIEF } : []) };
    }) as unknown as typeof fetch;
    render(<MemoryRouter><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}>
      <TaskProfilePanel taskId={71} isCreator onApplyWithQuestions={() => {}} /></AppProvider></MemoryRouter>);
    await screen.findByLabelText('需求九项');
    expect(screen.queryByRole('button', { name: '带着这些问题报名' })).toBeNull();
  });
});
