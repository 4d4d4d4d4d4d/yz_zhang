// SRCH-001/003 全站搜索在网页上的行为（101 号 spec）。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = {
  id: 2, phone: '138****0002', nickname: '找东西的人', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100,
  rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2',
};

const RESULTS = {
  tasks: [{ id: 7, title: '上门保洁两小时', category: '保洁', budget_cents: 20000, city: '上海' }],
  users: [{ id: 5, nickname: '王阿姨', skills: ['保洁', '收纳'], credit_score: 120, rating_avg: 4.9 }],
  contents: [{ id: 3, kind: 'post', title: '保洁验收怎么拍照', body: '前后对比…', author_id: 5 }],
  circles: [{ id: 1, name: '上海家政圈', kind: 'interest', member_count: 42 }],
};

function open(path: string, routes: Record<string, unknown>,
  calls: Array<{ path: string; query: string }> = []) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string) => {
    const [p, query = ''] = String(url).replace(/^.*\/api\/v1/, '').split('?');
    calls.push({ path: p, query });
    const hit = Object.keys(routes).find((k) => k === p);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : []) };
  }) as unknown as typeof fetch;
  const client = new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
  render(
    <MemoryRouter initialEntries={[path]}>
      <AppProvider client={client}><App /></AppProvider>
    </MemoryRouter>,
  );
  return calls;
}

describe('SRCH-001 全站搜索', () => {
  it('空框时显示热词，点一个就按它搜', async () => {
    const calls = open('/search', {
      '/users/me': ME, '/search/trending': [{ term: '保洁', count: 9 }], '/search': RESULTS,
    });
    fireEvent.click(await screen.findByText('保洁'));
    await waitFor(() => expect(screen.getByText('上门保洁两小时')).toBeTruthy());
    expect(calls.some((c) => c.path === '/search' && c.query.includes('q=%E4%BF%9D%E6%B4%81'))).toBe(true);
  });

  it('四类结果都画出来，人与任务能点进去', async () => {
    open('/search?q=保洁', { '/users/me': ME, '/search': RESULTS });
    const task = await screen.findByText('上门保洁两小时');
    expect(task.closest('a')?.getAttribute('href')).toBe('/tasks/7');
    expect(screen.getByText('王阿姨').closest('a')?.getAttribute('href')).toBe('/people/5');
    expect(screen.getByText('保洁验收怎么拍照')).toBeTruthy();
    expect(screen.getByText('上海家政圈')).toBeTruthy();
  });

  it('查询词在 URL 里：直接打开带 q 的链接就是那份结果', async () => {
    const calls = open('/search?q=收纳', { '/users/me': ME, '/search': RESULTS });
    await screen.findByText('上门保洁两小时');
    expect(calls.some((c) => c.path === '/search' && c.query.includes('q=%E6%94%B6%E7%BA%B3'))).toBe(true);
  });

  it('打字时给联想，点联想就按它搜', async () => {
    open('/search', {
      '/users/me': ME, '/search/suggest': ['保洁阿姨', '保洁验收'], '/search': RESULTS,
    });
    fireEvent.change(await screen.findByLabelText('全站搜索'), { target: { value: '保' } });
    fireEvent.click(await screen.findByText('保洁阿姨', {}, { timeout: 2000 }));
    await waitFor(() => expect(screen.getByText('上门保洁两小时')).toBeTruthy());
  });

  it('没有结果时说清楚，而不是一片空白', async () => {
    open('/search?q=火星', {
      '/users/me': ME, '/search': { tasks: [], users: [], contents: [], circles: [] },
    });
    await waitFor(() => expect(screen.getByText(/没有找到「火星」相关的结果/)).toBeTruthy());
  });

  it('导航栏常驻一个搜索入口', async () => {
    open('/', { '/users/me': ME, '/spaces': { items: [], next_cursor: null } });
    await waitFor(() => expect(screen.getByLabelText('搜索').getAttribute('href')).toBe('/search'));
  });
});
