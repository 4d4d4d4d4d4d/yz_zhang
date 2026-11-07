// SCN-294b（407 号 spec，V434）发单人按这一单加选资质：类目列了可加的才出勾选；勾了才带 task_certs；
// 换类目时上一个类目的勾选不带过去；任务详情写明这一单另外要什么证。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const USER = { id: 2, phone: '138****0002', nickname: '我', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [],
  credit_level: '普通', referral_code: 'r2', weekly_slots: [], limited_capacity: false };
const CATS = [
  { id: 1, name: '展台搭建', required_cert: '', optional_certs: ['高处作业操作证', '低压电工作业操作证'] },
  { id: 2, name: '无人机航拍', required_cert: '', optional_certs: ['民用无人机操控员执照'] },
  { id: 3, name: '文案写作', required_cert: '' },
];
type Call = { method: string; path: string; body?: Record<string, unknown> };

function open(path: string, calls: Call[], extra: (m: string, p: string) => unknown = () => undefined) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const hit = extra(method, p);
    const body = hit !== undefined ? hit : p === '/users/me' ? USER : p === '/categories' ? CATS : p === '/cities' ? [{ id: 1, name: '上海' }] : [];
    return { ok: true, status: 200, headers: { get: () => null }, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={[path]}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

afterEach(() => localStorage.clear());

describe('SCN-294b 发单人按这一单加选资质（407 号 spec）', () => {
  it('类目列了可加的才出勾选；勾了才带；换类目不带过去', async () => {
    const calls: Call[] = [];
    open('/publish', calls, (m, p) => (m === 'POST' && p === '/tasks' ? { id: 9, title: 'x', status: 'published' } : undefined));
    const title = await screen.findByLabelText('标题', {}, { timeout: 3000 });
    fireEvent.change(title, { target: { value: '展台背板 3 米高' } });
    fireEvent.change(screen.getByLabelText('类目'), { target: { value: '文案写作' } });
    expect(screen.queryByLabelText('这一单另外要的资质')).toBeNull();
    fireEvent.change(screen.getByLabelText('类目'), { target: { value: '展台搭建' } });
    const box = await screen.findByLabelText('这一单另外要的资质');
    fireEvent.click(within(box).getByLabelText(/高处作业操作证/));
    fireEvent.change(screen.getByLabelText('类目'), { target: { value: '无人机航拍' } });   // 换类目：高处作业证不带过去
    fireEvent.change(screen.getByLabelText('类目'), { target: { value: '展台搭建' } });
    const again = await screen.findByLabelText('这一单另外要的资质');
    expect((within(again).getByLabelText(/高处作业操作证/) as HTMLInputElement).checked).toBe(false);
    fireEvent.click(within(again).getByLabelText(/低压电工作业操作证/));
    // SCN-294d（408 号 spec）画像草稿也带上加选资质，风险里会说「没有的人报不了名」
    await waitFor(() => expect(calls.some((c) => c.path === '/profiles/task-draft'
      && JSON.stringify(c.body?.task_certs) === JSON.stringify(['低压电工作业操作证']))).toBe(true), { timeout: 3000 });
    fireEvent.click(screen.getByLabelText(/线上任务/));
    fireEvent.submit(title.closest('form')!);
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks')).toBeTruthy());
    expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks')!.body!.task_certs).toEqual(['低压电工作业操作证']);
  });

  it('没勾时请求体不带 task_certs', async () => {
    const calls: Call[] = [];
    open('/publish', calls, (m, p) => (m === 'POST' && p === '/tasks' ? { id: 9, title: 'x', status: 'published' } : undefined));
    const title = await screen.findByLabelText('标题', {}, { timeout: 3000 });
    fireEvent.change(title, { target: { value: '展位布置' } });
    fireEvent.change(screen.getByLabelText('类目'), { target: { value: '展台搭建' } });
    fireEvent.click(screen.getByLabelText(/线上任务/));
    fireEvent.submit(title.closest('form')!);
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks')).toBeTruthy());
    expect('task_certs' in calls.find((c) => c.method === 'POST' && c.path === '/tasks')!.body!).toBe(false);
  });

  it('任务详情写明这一单另外要什么证', async () => {
    open('/tasks/60', [], (_m, p) => p === '/tasks/60' ? { id: 60, title: '展台背板', description: '', category: '展台搭建', status: 'published',
      budget_cents: 20000, creator_id: 9, executor_id: null, is_remote: false, city: '上海', address_hint: '', address_exact: '', parent_id: null,
      task_type: 'service', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none', task_certs: ['高处作业操作证'] } : undefined);
    const line = await screen.findByLabelText('这一单另外要的资质');
    expect(line.textContent).toContain('这一单另外要「高处作业操作证」');
  });

  it('SCN-294e（413 号 spec）发单人看得到因为没证被排除了几个人，推荐一个都没有时也看得到', async () => {
    const calls: Call[] = [];
    open('/tasks/61', calls, (_m, p) => p === '/tasks/61' ? { id: 61, title: '展台背板', description: '', category: '展台搭建', status: 'published',
      budget_cents: 20000, creator_id: 2, executor_id: null, is_remote: false, city: '上海', address_hint: '', address_exact: '', parent_id: null,
      task_type: 'service', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none', task_certs: ['高处作业操作证'] }
      : p === '/tasks/61/recommendations/cert-gap' ? { required: ['高处作业操作证'], task_certs: ['高处作业操作证'], pool: 4, eligible: 0, excluded: 4,
        only_missing: [{ cert: '高处作业操作证', count: 3 }] } : undefined);
    const line = await screen.findByTestId('cert-gap', {}, { timeout: 3000 });
    expect(line.textContent).toBe('现在没有人同时有「高处作业操作证」，4 个人因此没进推荐；其中 3 人只差你加选的「高处作业操作证」。这张证真用不上的话，下次发单别勾');
    expect(screen.getByText('AI 推荐人选')).toBeTruthy();
  });

  it('SCN-294c（414 号 spec）只差加选的那一张：一键去掉，请求只去这一张', async () => {
    const calls: Call[] = [];
    open('/tasks/62', calls, (m, p) => p === '/tasks/62' && m === 'GET' ? { id: 62, title: '展台背板', description: '', category: '展台搭建', status: 'published',
      budget_cents: 20000, creator_id: 2, executor_id: null, is_remote: false, city: '上海', address_hint: '', address_exact: '', parent_id: null,
      task_type: 'service', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none', task_certs: ['高处作业操作证', '低压电工作业操作证'] }
      : p === '/tasks/62' && m === 'PATCH' ? { id: 62, task_certs: ['低压电工作业操作证'] }
      : p === '/tasks/62/recommendations/cert-gap' ? { required: ['高处作业操作证', '低压电工作业操作证'], task_certs: ['高处作业操作证', '低压电工作业操作证'],
        pool: 4, eligible: 0, excluded: 4, only_missing: [{ cert: '高处作业操作证', count: 3 }] } : undefined);
    fireEvent.click(await screen.findByText('这一单不要「高处作业操作证」了', {}, { timeout: 3000 }));
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH' && c.path === '/tasks/62')).toBeTruthy());
    expect(calls.find((c) => c.method === 'PATCH')!.body).toEqual({ task_certs: ['低压电工作业操作证'] });
    expect(screen.queryByText('这一单不要「低压电工作业操作证」了')).toBeNull();   // 没人只差这一张，不给按钮
  });

  it('SCN-294f（426 号 spec）发单人发布后能加上类目列出的资质；加不上时说清为什么', async () => {
    const calls: Call[] = [];
    open('/tasks/63', calls, (m, p) => p === '/tasks/63' && m === 'GET' ? { id: 63, title: '展台背板', description: '', category: '展台搭建', status: 'published',
      budget_cents: 20000, creator_id: 2, executor_id: null, is_remote: false, city: '上海', address_hint: '', address_exact: '', parent_id: null,
      task_type: 'service', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none', task_certs: ['高处作业操作证'] }
      : p === '/tasks/63' && m === 'PATCH' ? { __status: 409 } : undefined);
    const box = await screen.findByLabelText('加上这一单另外要的资质', {}, { timeout: 3000 });
    expect(within(box).queryByText('加上「高处作业操作证」')).toBeNull();
    fireEvent.click(within(box).getByText('加上「低压电工作业操作证」'));
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH' && c.path === '/tasks/63')).toBeTruthy());
    expect(calls.find((c) => c.method === 'PATCH')!.body).toEqual({ task_certs: ['高处作业操作证', '低压电工作业操作证'] });
  });
});
