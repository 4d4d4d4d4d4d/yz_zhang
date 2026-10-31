// SCN-116 多天名额按天汇总（174 号 spec）：详情页上看得到哪天还缺几个人；单天多人照旧只有一排名额。
import { PlatformClient } from '@platform/core';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = {
  id: 2, phone: '138****0002', nickname: '店主', bio: '', city: '上海', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100,
  rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2',
};
const PARENT = { id: 30, title: '快闪店帮手', description: '', category: '跑腿', status: 'draft', budget_cents: 10000,
  creator_id: 2, executor_id: null, is_remote: false, city: '上海', address_hint: '', address_exact: '', parent_id: null,
  task_type: 'service', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none', days: 2, work_date: '2030-01-05' };
const child = (id: number, date: string | null, status: string) => ({ id, title: `名额 ${id}`, status, budget_cents: 2500,
  depends_on: [], executor_id: status === 'published' ? null : 5, work_date: date });

function open(tree: unknown) {
  localStorage.setItem('token', 'tok');
  const routes: Record<string, unknown> = { '/users/me': ME, '/tasks/30': PARENT, '/tasks/30/tree': tree };
  const fetchImpl = vi.fn(async (url: string) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    return { ok: true, status: 200, text: async () => JSON.stringify(routes[p] ?? []) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/tasks/30']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('SCN-116 按天看名额', () => {
  it('一天一行，哪天还缺几个人；标题旁说有几天缺人', async () => {
    open({ parent_id: 30, parent_status: 'draft', progress_pct: 0, all_children_completed: false,
      children: [child(31, '2030-01-05', 'matched'), child(32, '2030-01-05', 'matched'), child(33, '2030-01-06', 'published'), child(34, '2030-01-06', 'matched')],
      by_day: [{ date: '2030-01-05', slots: 2, filled: 2, open: 0, done: 0, closed: 0 },
        { date: '2030-01-06', slots: 2, filled: 1, open: 1, done: 0, closed: 0 }] });
    const box = await screen.findByLabelText('按天看名额');
    expect(box.textContent).toContain('还有 1 天缺人');
    expect(box.textContent).toContain('01-05 · 2 个名额：招到 2，不缺人了');
    expect(box.textContent).toContain('01-06 · 2 个名额：招到 1，还缺 1');
  });

  it('单天多人没有按天汇总：只有一排名额', async () => {
    open({ parent_id: 30, parent_status: 'draft', progress_pct: 0, all_children_completed: false,
      children: [child(31, null, 'published'), child(32, null, 'published')], by_day: [] });
    await screen.findByText('名额 31');
    expect(screen.queryByLabelText('按天看名额')).toBeNull();
  });
});
