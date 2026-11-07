// CNT-023 / CNT-024 关注列表与内容流里的关注状态（102 号 spec）。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = {
  id: 2, phone: '138****0002', nickname: '我', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100,
  rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2',
};

const post = (id: number, author_id: number, nick: string, followed: boolean | null) => ({
  id, author_id, author_nickname: nick, kind: 'post', title: '', body: `正文${id}`, tags: [],
  visibility: 'public', circle_id: null, linked_category: '', media_urls: [], status: 'published',
  source_task_id: null, like_count: 0, comment_count: 0, liked_by_me: false,
  author_followed_by_viewer: followed, created_at: '2026-10-10T00:00:00Z',
});

function open(path: string, routes: Record<string, unknown>,
  calls: Array<{ method: string; path: string }> = [],
  errors: Record<string, { status: number; code: string; message: string }> = {}) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p });
    const err = errors[p];
    if (err) return { ok: false, status: err.status, text: async () => JSON.stringify({ detail: { code: err.code, message: err.message } }) };
    const key = Object.keys(routes).find((k) => k === `${method} ${p}`) ?? Object.keys(routes).find((k) => k === p);
    return { ok: true, status: 200, text: async () => JSON.stringify(key ? routes[key] : []) };
  }) as unknown as typeof fetch;
  const client = new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
  render(<MemoryRouter initialEntries={[path]}><AppProvider client={client}><App /></AppProvider></MemoryRouter>);
  return calls;
}

describe('CNT-024 内容流里的关注按钮有状态', () => {
  it('已关注的作者显示「已关注」，点它是取消关注；同作者的几条一起变', async () => {
    const calls: Array<{ method: string; path: string }> = [];
    open('/community', {
      '/users/me': ME,
      '/feed': [post(1, 5, '甲', true), post(2, 5, '甲', true), post(3, 6, '乙', false), post(4, 2, '我', null)],
      'DELETE /users/5/follow': { following: false },
    }, calls);
    // 页面顶部有一个叫「关注」的分区标签，所以按 aria-pressed 找关注按钮
    await screen.findByText('正文1');
    const pressed = () => Array.from(document.querySelectorAll('button[aria-pressed="true"]'));
    const unpressed = () => Array.from(document.querySelectorAll('button[aria-pressed="false"]'));
    expect(pressed()).toHaveLength(2);
    expect(unpressed()).toHaveLength(1);
    expect(pressed()[0].textContent).toBe('已关注');
    fireEvent.click(pressed()[0]);
    await waitFor(() => expect(unpressed()).toHaveLength(3));
    expect(calls.some((c) => c.method === 'DELETE' && c.path === '/users/5/follow')).toBe(true);
    // 不重新拉整页
    expect(calls.filter((c) => c.path === '/feed')).toHaveLength(1);
  });

  it('自己的内容不画关注按钮（null）', async () => {
    open('/community', { '/users/me': ME, '/feed': [post(4, 2, '我', null)] });
    await screen.findByText('正文4');
    expect(document.querySelectorAll('button[aria-pressed]')).toHaveLength(0);
  });
});

describe('CNT-023 关注 / 粉丝列表', () => {
  const page = (items: Array<[number, string, boolean | null]>, next: number | null) => ({
    items: items.map(([user_id, nickname, viewer_following]) => ({
      user_id, nickname, followed_at: '2026-10-10T00:00:00Z', viewer_following })),
    next_cursor: next,
  });

  it('列出关注者，每个人旁边的按钮有状态，能翻页', async () => {
    const calls: Array<{ method: string; path: string }> = [];
    open('/people/9/follows?tab=followers', {
      '/users/me': ME, '/users/9/followers': page([[11, '粉丝甲', true], [12, '粉丝乙', false]], 30),
    }, calls);
    expect((await screen.findByText('粉丝甲')).closest('a')?.getAttribute('href')).toBe('/people/11');
    expect(screen.getByText('已关注')).toBeTruthy();
    fireEvent.click(screen.getByText('加载更多'));
    await waitFor(() => expect(calls.filter((c) => c.path === '/users/9/followers')).toHaveLength(2));
  });

  it('对方资料不公开时把服务端的话显示出来', async () => {
    open('/people/9/follows?tab=following', { '/users/me': ME }, [],
      { '/users/9/following': { status: 403, code: 'follow_list_private', message: '对方未公开资料，看不到关注列表' } });
    await waitFor(() => expect(screen.getByText(/对方未公开资料/)).toBeTruthy());
  });

  it('切到「正在关注」打的是另一个接口', async () => {
    const calls: Array<{ method: string; path: string }> = [];
    open('/people/9/follows?tab=followers', {
      '/users/me': ME, '/users/9/followers': page([], null), '/users/9/following': page([[13, '他关注的人', null]], null),
    }, calls);
    fireEvent.click(await screen.findByRole('tab', { name: '正在关注' }));
    await waitFor(() => expect(screen.getByText('他关注的人')).toBeTruthy());
    expect(calls.some((c) => c.path === '/users/9/following')).toBe(true);
  });
});
