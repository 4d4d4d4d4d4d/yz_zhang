// SCN-120 一单多次上门的逐次回报（176 号 spec）：发布页写上门次数与清单；详情页接单人勾清单交回报，双方看到漏了什么。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 2, phone: '138****0002', nickname: '宠托师', bio: '', city: '上海', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2' };
type Call = { method: string; path: string; body?: unknown };
const TASK = { id: 70, title: '上门喂猫 7 天', description: '', category: '宠物照护', status: 'in_progress', budget_cents: 50000,
  creator_id: 9, executor_id: 2, is_remote: false, city: '上海', address_hint: '', address_exact: '', parent_id: null,
  task_type: 'service', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none',
  visits_planned: 14, visit_checklist: ['喂食', '换水', '铲屎'] };
const VISITS = { task_id: 70, planned: 14, checklist: ['喂食', '换水', '铲屎'], reported: 1, missed_total: 1,
  visits: [{ n: 1, id: 5, created_at: '2030-01-05T02:00:00Z', done: ['喂食', '铲屎'], missed: ['换水'], note: '猫很精神', images: [] }] };

function open(path: string, calls: Call[], routes: Record<string, unknown> = {}) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const key = `${method} ${p}`;
    const body = key in routes ? routes[key] : p === '/users/me' ? ME : p === '/categories' ? [{ name: '宠物照护', required_cert: '' }]
      : p === '/cities' ? [{ id: 1, name: '上海' }] : method === 'POST' && p === '/tasks' ? { id: 71, title: 'x', status: 'published' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={[path]}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('SCN-120 上门回报', () => {
  it('发布页：上门次数与清单（顿号分开）带进请求；不填不带', async () => {
    const calls: Call[] = [];
    open('/publish?title=%E5%96%82%E7%8C%AB&category=%E5%AE%A0%E7%89%A9%E7%85%A7%E6%8A%A4&city=%E4%B8%8A%E6%B5%B7', calls);
    await screen.findByDisplayValue('喂猫');
    fireEvent.change(screen.getByLabelText('要上门几次'), { target: { value: '14' } });
    fireEvent.change(screen.getByLabelText('每次要做的事'), { target: { value: '喂食、换水，铲屎' } });
    fireEvent.change(screen.getByDisplayValue('— 请选择 —'), { target: { value: 'assign' } });
    fireEvent.submit(screen.getByLabelText('要上门几次').closest('form')!);
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks')?.body).toMatchObject(
      { visits_planned: 14, visit_checklist: ['喂食', '换水', '铲屎'] }));
  });

  it('详情页：看到回报了几次、漏了什么；接单人勾清单交这次的回报', async () => {
    const calls: Call[] = [];
    open('/tasks/70', calls, { 'GET /tasks/70': TASK, 'GET /tasks/70/visits': VISITS, 'POST /tasks/70/visits': { n: 2, id: 6, done: ['喂食'], missed: [] } });
    const panel = await screen.findByLabelText('上门回报');
    await waitFor(() => expect(panel.textContent).toContain('上门回报 · 1/14 次'));
    expect(panel.textContent).toContain('一共有 1 项没做');
    expect(panel.textContent).toContain('已做：喂食、铲屎；没做：换水 · 猫很精神');
    fireEvent.click(screen.getByLabelText('做了：喂食'));
    fireEvent.click(screen.getByLabelText('做了：换水'));
    fireEvent.change(screen.getByLabelText('这次的备注'), { target: { value: '一切正常' } });
    fireEvent.click(screen.getByText('交这次的上门回报'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks/70/visits')?.body).toEqual(
      { done: ['喂食', '换水'], note: '一切正常', images: [] }));
  });

  it('发单人只看、不交', async () => {
    open('/tasks/70', [], { 'GET /tasks/70': { ...TASK, creator_id: 2, executor_id: 5 }, 'GET /tasks/70/visits': VISITS });
    await screen.findByLabelText('上门回报');
    expect(screen.queryByText('交这次的上门回报')).toBeNull();
  });

  it('没写上门次数和清单的单没有这一块', async () => {
    open('/tasks/70', [], { 'GET /tasks/70': { ...TASK, visits_planned: 0, visit_checklist: [] } });
    await screen.findByText('上门喂猫 7 天');
    expect(screen.queryByLabelText('上门回报')).toBeNull();
  });
});
