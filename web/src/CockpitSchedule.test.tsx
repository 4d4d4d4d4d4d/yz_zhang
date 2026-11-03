// AI-DEC-021b（368 号 spec）：驾驶舱里后一步的截止不晚于它要等的前一步，标红并写清。
import { PlatformClient } from '@platform/core';
import { render, screen, within } from '@testing-library/react';
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
const node = (id: number, title: string) => ({ id, parent_id: 20, title, status: 'published', status_name: '招募中', budget_cents: 300000,
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


describe('AI-DEC-021b 驾驶舱的排期冲突（368 号 spec）', () => {
  const conflict = (extra: Record<string, unknown> = {}) => ({ ...COCKPIT(0),
    alerts: [{ task_id: 22, kind: 'schedule_conflict', text: '「页面开发」的截止不晚于它要等的「需求梳理」：前一步做完才能开始，改一下这一步的截止' },
      { task_id: 22, kind: 'to_accept', text: '「页面开发」已交付，等你验收' }],
    nodes: [{ ...node(21, '需求梳理'), deadline: '2026-11-10T10:00:00+00:00', schedule_conflicts: [] },
      { ...node(22, '页面开发'), deadline: '2026-11-09T10:00:00+00:00', depends_on: [21], blocked_by: [21], schedule_conflicts: [21], ...extra }] });

  it('排期冲突的预警标红，截止那一格写清不晚于哪一步；别的预警照旧不标红', async () => {
    open(conflict());
    const alerts = await screen.findByLabelText('需要你出手');
    const items = alerts.querySelectorAll('li');
    expect(items[0].className).toBe('error');
    expect(items[1].className).toBe('');
    const row = within(screen.getByLabelText('每一步')).getByText('页面开发', { selector: 'a' }).closest('tr')!;
    expect(row.textContent).toContain('（不晚于要等的「需求梳理」）');
    expect(row.querySelectorAll('td')[4].className).toBe('error');
    const ok = within(screen.getByLabelText('每一步')).getByText('需求梳理', { selector: 'a' }).closest('tr')!;
    expect(ok.querySelectorAll('td')[4].className).toBe('');
  });

  it('老服务端没有 schedule_conflicts 字段：驾驶舱照常显示，不白屏', async () => {
    open(conflict({ schedule_conflicts: undefined }));
    await screen.findByLabelText('合作驾驶舱');
    const row = within(screen.getByLabelText('每一步')).getByText('页面开发', { selector: 'a' }).closest('tr')!;
    expect(row.textContent).not.toContain('不晚于');
  });
});
