// AI-DEC-021c（384 号 spec）：驾驶舱时间线——每一步一条，预计哪天做完；没开工的步骤直接填工期。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = {
  id: 2, phone: '138****0002', nickname: '我', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100,
  rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2',
};
const PARENT = { id: 20, title: '公司官网', description: '', category: '软件开发', status: 'published', budget_cents: 800000,
  creator_id: 2, executor_id: null, is_remote: true, city: '', address_hint: '', address_exact: '', parent_id: null,
  task_type: 'project', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none' };
const node = (id: number, title: string, extra: Record<string, unknown> = {}) => ({ id, parent_id: 20, title, status: 'published',
  status_name: '招募中', budget_cents: 300000, is_container: false, depends_on: [], blocked_by: [], executor_id: null,
  executor_nickname: null, deadline: null, overdue: false, on_critical_path: false, in_dispute: false, schedule_conflicts: [], ...extra });
const BASE = { task_id: 20, title: '公司官网', status: 'published', progress_pct: 0, steps_total: 2, steps_done: 0,
  budget: { planned_cents: 800000, allocated_cents: 600000, committed_cents: 0, paid_cents: 0, remaining_cents: 800000 },
  critical_path: [21, 22], alerts: [] };
const TREE = { parent_id: 20, parent_status: 'published', progress_pct: 0, all_children_completed: false,
  children: [{ id: 21, title: '需求梳理', status: 'published', budget_cents: 300000, depends_on: [], executor_id: null }] };

function open(cockpit: unknown) {
  localStorage.setItem('token', 'tok');
  const calls: Array<{ method: string; path: string; body: unknown }> = [];
  const routes: Record<string, unknown> = { '/users/me': ME, '/tasks/20': PARENT, '/tasks/20/cockpit': cockpit, '/tasks/20/tree': TREE };
  const fetchImpl = vi.fn(async (url: string, init?: RequestInit) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path: p, body: init?.body ? JSON.parse(String(init.body)) : null });
    return { ok: true, status: 200, text: async () => JSON.stringify(routes[p] ?? []) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/tasks/20']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
  return calls;
}

describe('AI-DEC-021c 驾驶舱时间线（384 号 spec）', () => {
  it('每一步一条：后一步接在前一步后面，赶不上自己截止的标红，写出预计完成日', async () => {
    open({ ...BASE,
      nodes: [node(21, '需求梳理', { est_days: 2 }), node(22, '页面开发', { est_days: 8, depends_on: [21], blocked_by: [21] })],
      alerts: [{ task_id: 20, kind: 'projected_late', text: '按各步的工期估计排下来，整件事会晚于截止' }],
      timeline: { projected_finish: '2026-11-20T12:00:00Z', unknown_steps: [], rows: [
        { task_id: 21, start: '2026-11-10T12:00:00Z', end: '2026-11-12T12:00:00Z', basis: 'estimate', late: false },
        { task_id: 22, start: '2026-11-12T12:00:00Z', end: '2026-11-20T12:00:00Z', basis: 'estimate', late: true }] } });
    const tl = await screen.findByLabelText('时间线');
    expect(tl.textContent).toMatch(/按各步工期排下来，预计 .*20.* 做完/);
    const rows = tl.querySelectorAll('div.row');
    expect(rows).toHaveLength(2);
    const bar = (i: number) => rows[i].querySelector(':scope > div > div') as HTMLElement;
    expect(bar(0).style.left).toBe('0%');
    expect(bar(0).style.width).toBe('20%');
    expect(bar(1).style.left).toBe('20%');
    expect(rows[1].getAttribute('data-late')).toBe('true');
    expect(rows[1].textContent).toContain('赶不上截止');
    expect(rows[0].getAttribute('data-late')).toBeNull();
    expect(bar(1).title).toContain('按工期估计（赶不上这一步的截止）');
    // 按工期赶不上截止的预警标红
    expect((await screen.findByLabelText('需要你出手')).querySelector('li')!.className).toBe('error');
  });

  it('排不出来时说清几步没填工期；没开工的步骤在表里直接填工期，存完重新取驾驶舱', async () => {
    const calls = open({ ...BASE, nodes: [node(21, '需求梳理'), node(22, '页面开发', { status: 'in_progress', status_name: '进行中', est_days: 5 })],
      timeline: { projected_finish: null, unknown_steps: [21], rows: [
        { task_id: 21, start: null, end: null, basis: 'unknown', late: false },
        { task_id: 22, start: '2026-11-10T12:00:00Z', end: '2026-11-15T12:00:00Z', basis: 'estimate', late: false }] } });
    const tl = await screen.findByLabelText('时间线');
    expect(tl.textContent).toContain('有 1 步没填工期也没填截止');
    const table = screen.getByLabelText('每一步');
    const row = (t: string) => within(table).getByText(t, { selector: 'a' }).closest('tr')!;
    // 开工以后只读
    expect(within(row('页面开发')).queryByLabelText('工期（天）')).toBeNull();
    expect(row('页面开发').textContent).toContain('5 天');
    const input = within(row('需求梳理')).getByLabelText('工期（天）');
    const save = within(row('需求梳理')).getByText('存');
    fireEvent.change(input, { target: { value: '0' } });
    expect((save as HTMLButtonElement).disabled).toBe(true);
    expect(row('需求梳理').textContent).toContain('1~365 天');
    fireEvent.change(input, { target: { value: '3' } });
    const before = calls.filter((c) => c.path === '/tasks/20/cockpit').length;
    fireEvent.click(save);
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH' && c.path === '/tasks/21')).toBe(true));
    expect(calls.find((c) => c.method === 'PATCH')!.body).toEqual({ est_days: 3 });
    await waitFor(() => expect(calls.filter((c) => c.path === '/tasks/20/cockpit').length).toBe(before + 1));
  });

  it('老服务端没有时间线：驾驶舱照常显示，不画时间线', async () => {
    open({ ...BASE, nodes: [node(21, '需求梳理'), node(22, '页面开发')] });
    await screen.findByLabelText('合作驾驶舱');
    expect(screen.queryByLabelText('时间线')).toBeNull();
  });
});
