// NTF-068 公告按类目定向（238 号 spec）。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ADMIN = { id: 1, phone: '138****0001', nickname: '运营', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['ops'], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r1' };
const SENT = { id: 5, title: '跑腿规则调整', body: '', verified_only: false, city: '', audience: 'workers', category: '跑腿', status: 'sent',
  scheduled_at: null, created_by: 1, created_at: '2026-10-14T00:00:00Z', sent_at: '2026-10-14T00:00:00Z', delivered: 80, closed_by: null,
  closed_at: null, close_reason: '', read: 0, read_rate: 0 };

type Call = { method: string; path: string; body: unknown };
function open(calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    const body: unknown = path === '/users/me' ? ADMIN
      : path === '/categories' ? [{ id: 1, name: '跑腿', required_cert: '' }, { id: 2, name: '设计', required_cert: '' }]
      : method === 'GET' && path === '/admin/announcements' ? [SENT, { ...SENT, id: 6, title: '多类目', categories: ['跑腿', '设计'] }]
      : path === '/admin/announcements/preview' ? { audience: 80, verified_only: false, city: '', audience_kind: 'workers', category: '跑腿',
        title: '跑腿规则调整', body: '', warnings: [] }
      : method === 'POST' && path === '/admin/announcements' ? { delivered: 80, id: 6, status: 'sent', scheduled_at: null }
      : path === '/admin/announcements/6/read-by-category' ? { announcement_id: 6, overlap: 1, note: '',
          categories: [{ category: '跑腿', delivered: 2, read: 1, read_rate: 0.5 }, { category: '设计', delivered: 2, read: 2, read_rate: 1 }] }
      : path === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('NTF-068 公告按类目定向', () => {
  it('选了类目才带 category，预览与历史都说清是哪个类目', async () => {
    const calls: Call[] = [];
    open(calls);
    const card = await screen.findByLabelText('全站公告');
    fireEvent.change(within(card).getByPlaceholderText('标题'), { target: { value: '跑腿规则调整' } });
    fireEvent.click(within(card).getByText('预览'));
    await waitFor(() => expect(calls.filter((c) => c.path === '/admin/announcements/preview')).toHaveLength(1));
    expect(calls.find((c) => c.path === '/admin/announcements/preview')?.body).not.toHaveProperty('category');
    fireEvent.change(await within(card).findByLabelText('只发给类目'), { target: { value: '跑腿' } });
    fireEvent.change(within(card).getByLabelText('发给哪类人'), { target: { value: 'workers' } });
    fireEvent.click(within(card).getByText('预览'));
    await waitFor(() => expect(calls.filter((c) => c.path === '/admin/announcements/preview')).toHaveLength(2));
    expect(calls.filter((c) => c.path === '/admin/announcements/preview')[1].body).toMatchObject({ category: '跑腿', audience: 'workers' });
    expect((await screen.findByTestId('ann-preview')).textContent).toContain('近 180 天报过名接单的人 · 类目「跑腿」');
    fireEvent.click(within(card).getByText('发布'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/admin/announcements')?.body)
      .toMatchObject({ category: '跑腿', audience: 'workers' }));
    expect((await screen.findByLabelText('发过的公告')).textContent).toContain('（类目「跑腿」）');
  });

  it('NTF-070 选了类目后可以「也发给」别的类目；没勾不带 categories，勾了带上，历史写明全部类目', async () => {
    const calls: Call[] = [];
    open(calls);
    const card = await screen.findByLabelText('全站公告');
    fireEvent.change(within(card).getByPlaceholderText('标题'), { target: { value: '规则调整' } });
    expect(within(card).queryByLabelText('也发给类目')).toBeNull();
    fireEvent.change(await within(card).findByLabelText('只发给类目'), { target: { value: '跑腿' } });
    fireEvent.click(within(card).getByText('预览'));
    await waitFor(() => expect(calls.filter((c) => c.path === '/admin/announcements/preview')).toHaveLength(1));
    expect(calls.find((c) => c.path === '/admin/announcements/preview')?.body).not.toHaveProperty('categories');
    fireEvent.click(within(within(card).getByLabelText('也发给类目')).getByLabelText('设计'));
    fireEvent.click(within(card).getByText('预览'));
    await waitFor(() => expect(calls.filter((c) => c.path === '/admin/announcements/preview')).toHaveLength(2));
    expect(calls.filter((c) => c.path === '/admin/announcements/preview')[1].body).toMatchObject({ category: '跑腿', categories: ['设计'] });
    fireEvent.click(within(card).getByText('发布'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/admin/announcements')?.body)
      .toMatchObject({ category: '跑腿', categories: ['设计'] }));
    expect((await screen.findByLabelText('发过的公告')).textContent).toContain('（类目「跑腿、设计」）');
  });

  it('NTF-071 多类目的公告能分类目看阅读率；单类目的不显示', async () => {
    const calls: Call[] = [];
    open(calls);
    const table = await screen.findByLabelText('发过的公告');
    const btns = await within(table).findAllByText('分类目');
    expect(btns).toHaveLength(1);
    fireEvent.click(btns[0]);
    const box = await screen.findByTestId('cat-reads-6');
    expect(box.textContent).toContain('跑腿：1/2 人（50%）');
    expect(box.textContent).toContain('设计：2/2 人（100%）');
    expect(box.textContent).toContain('1 人同时属于几个类目');
  });
});

