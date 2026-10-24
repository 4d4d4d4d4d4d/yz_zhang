// AGT-090 结项报告（132 号 spec）：合作驾驶舱里全部步骤完成后出现，实付按合约放款算。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = {
  id: 2, phone: '138****0002', nickname: '我', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100,
  rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2',
};
const PARENT = { id: 20, title: '公司官网', description: '', category: '软件开发', status: 'completed', budget_cents: 800000,
  creator_id: 2, executor_id: null, is_remote: true, city: '', address_hint: '', address_exact: '', parent_id: null,
  task_type: 'project', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none' };
const node = (id: number, title: string) => ({ id, parent_id: 20, title, status: 'completed', status_name: '已完成', budget_cents: 300000,
  is_container: false, depends_on: [], blocked_by: [], executor_id: 5, executor_nickname: '陈设计', deadline: null, overdue: false,
  on_critical_path: false, in_dispute: false });
const COCKPIT = (done: number) => ({ task_id: 20, title: '公司官网', status: 'completed', progress_pct: 100, steps_total: 2, steps_done: done,
  budget: { planned_cents: 800000, allocated_cents: 600000, committed_cents: 0, paid_cents: 580000, remaining_cents: 220000 },
  critical_path: [], alerts: [], nodes: [node(21, '需求梳理'), node(22, '页面开发')] });
const REPORT = { task_id: 20, title: '公司官网', status: 'completed', summary: '共 2 个子任务，完成 2 个，实际支出 6000.00 元（计划预算 8000.00 元）',
  total_cost_cents: 600000, planned_budget_cents: 800000, duration_days: 12, children_completed: 2, children_total: 2,
  deliverables: [{ task_id: 21, title: '需求梳理', executor_id: 5, cost_cents: 300000, status: 'completed' }],
  paid_cents: 580000, ready: true };
const TREE = { parent_id: 20, parent_status: 'completed', progress_pct: 100, all_children_completed: true,
  children: [{ id: 21, title: '需求梳理', status: 'completed', budget_cents: 300000, depends_on: [], executor_id: 5 }] };

function open(cockpit: unknown) {
  localStorage.setItem('token', 'tok');
  const routes: Record<string, unknown> = { '/users/me': ME, '/tasks/20': PARENT, '/tasks/20/cockpit': cockpit, '/tasks/20/tree': TREE, '/tasks/20/final-report': REPORT };
  const fetchImpl = vi.fn(async (url: string) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    return { ok: true, status: 200, text: async () => JSON.stringify(routes[p] ?? []) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/tasks/20']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('AGT-090 结项报告', () => {
  it('全部步骤完成：看结项报告，实付按合约放款、用时、交付清单', async () => {
    open(COCKPIT(2));
    fireEvent.click(await screen.findByRole('button', { name: '看结项报告' }));
    const r = await screen.findByLabelText('结项报告');
    expect(r.textContent).toContain('实付（按合约放款）¥5800.00 · 计划 ¥8000.00 · 用时 12 天');
    expect(r.textContent).toContain('需求梳理');
  });

  it('还有步骤没完成：不出现结项报告', async () => {
    open(COCKPIT(1));
    await screen.findByLabelText('合作驾驶舱');
    expect(screen.queryByRole('button', { name: '看结项报告' })).toBeNull();
  });
});
