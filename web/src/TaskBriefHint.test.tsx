// SCN-110 任务详情上的创作类需求九项（194 号 spec）：接单的人看到「报名前可以先问问发单人」，发单人自己看到「还可以补」。
import { PlatformClient } from '@platform/core';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
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
