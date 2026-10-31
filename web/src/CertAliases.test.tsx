// SCN-213（334 号 spec）后台资质别名：列出内置的与后台配的；提出要两个名字和理由；自己提出的看不到「确认」；能收回。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 2, phone: '138****0002', nickname: '运营', bio: '', city: '上海', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['ops'], credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [],
  credit_level: '普通', referral_code: 'r2' };
const LIST = { builtin: [['低压电工作业操作证', '电工']], items: [
  { id: 7, a: '焊工证', b: '熔化焊接与热切割作业操作证', reason: '俗称', status: 'pending', proposed_by: 2, created_at: '2026-10-28T00:00:00Z' },
  { id: 8, a: '甲证', b: '乙证', reason: '同一张', status: 'pending', proposed_by: 9, created_at: '2026-10-28T00:00:00Z' },
] };
type Call = { method: string; path: string; body?: unknown };

function open(calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const body = p === '/users/me' ? ME : p === '/admin/cert-aliases' && method === 'GET' ? LIST : p === '/categories' ? []
      : p === '/admin/admins' ? { admins: [] } : p === '/admin/aml/activities' ? { items: [], note: '' }
      : p.startsWith('/admin/cert-aliases') ? LIST.items[1] : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('SCN-213 资质别名', () => {
  it('列出内置的；自己提出的没有「确认」，别人提出的可以确认；能收回', async () => {
    const calls: Call[] = [];
    open(calls);
    const box = await screen.findByLabelText('资质别名');
    expect(box.textContent).toContain('低压电工作业操作证 = 电工');
    const mine = within(box).getByText(/焊工证 = 熔化焊接与热切割作业操作证/).closest('li')!;
    expect(within(mine).queryByText('确认')).toBeNull();
    const other = within(box).getByText(/甲证 = 乙证/).closest('li')!;
    fireEvent.click(within(other).getByText('确认'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/admin/cert-aliases/8/approve')).toBe(true));
    fireEvent.click(within(mine).getByText('收回'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/admin/cert-aliases/7/revoke')).toBe(true));
  });

  it('提出：两个名字和理由都写了才能点', async () => {
    const calls: Call[] = [];
    open(calls);
    const box = await screen.findByLabelText('资质别名');
    const btn = within(box).getByText('提出') as HTMLButtonElement;
    fireEvent.change(within(box).getByLabelText('资质名甲'), { target: { value: '丙证' } });
    fireEvent.change(within(box).getByLabelText('资质名乙'), { target: { value: '丁证' } });
    expect(btn.disabled).toBe(true);
    fireEvent.change(within(box).getByLabelText('理由'), { target: { value: '证上写的是丁证' } });
    expect(btn.disabled).toBe(false);
    fireEvent.click(btn);
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/admin/cert-aliases')?.body)
      .toEqual({ a: '丙证', b: '丁证', reason: '证上写的是丁证' }));
  });
});
