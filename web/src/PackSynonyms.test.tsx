// PACK-092c（436 号 spec）后台近义说法：列出生效的表与后台提出的行；自己提出的看不到「确认」；
// 提出时写法按逗号拆开；能收回；能试一句看会多带上哪些写法。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PackSynonyms } from './AdminPacks';
import { AppProvider } from './store';

const ME = { id: 2, phone: '138****0002', nickname: '运营', bio: '', city: '上海', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['ops'], credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [],
  credit_level: '普通', referral_code: 'r2' };
const LIST = {
  effective: [
    { name: '下雨', words: ['下雨', '暴雨'], includes: [] },
    { name: '天气不好', words: ['天气不好', '变天'], includes: ['下雨'] },
  ],
  items: [
    { id: 7, name: '大风', words: ['风力'], includes: [], reason: '无人机写风力', status: 'pending', proposed_by: 2, created_at: '2026-11-07T00:00:00Z' },
    { id: 8, name: '下雪', words: ['飘雪'], includes: [], reason: '口语里常说', status: 'pending', proposed_by: 9, created_at: '2026-11-07T00:00:00Z' },
  ],
};
type Call = { method: string; path: string; body?: unknown; query?: string };

function open(calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const [path, query] = String(url).replace(/^.*\/api\/v1/, '').split('?');
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : undefined, query });
    const body = path === '/users/me' ? ME : path === '/admin/pack-synonyms' && method === 'GET' ? LIST
      : path === '/admin/pack-synonyms/expand' ? { q: '天气不好', words: ['变天', '下雨', '暴雨'] }
      : path.startsWith('/admin/pack-synonyms') ? LIST.items[1] : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><PackSynonyms /></AppProvider>);
}

describe('PACK-092c 近义说法', () => {
  it('列出生效的表；自己提出的没有「确认」，别人提出的可以确认；能收回', async () => {
    const calls: Call[] = [];
    open(calls);
    const box = await screen.findByLabelText('近义说法');
    const table = within(box).getByLabelText('生效的近义表');
    expect(table.textContent).toContain('下雨：下雨、暴雨');
    expect(table.textContent).toContain('还包含 下雨');
    await waitFor(() => expect(calls.some((c) => c.path === '/users/me')).toBe(true));
    const mine = within(box).getByText(/大风 \+ 风力/).closest('li')!;
    await waitFor(() => expect(within(mine).queryByText('确认')).toBeNull());
    const theirs = within(box).getByText(/下雪 \+ 飘雪/).closest('li')!;
    fireEvent.click(within(theirs).getByText('确认'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/admin/pack-synonyms/8/approve')).toBe(true));
    fireEvent.click(within(mine).getByText('收回'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/admin/pack-synonyms/7/revoke')).toBe(true));
  });

  it('提出时写法按逗号拆开；理由太短不让提；试一句看会多带上哪些写法', async () => {
    const calls: Call[] = [];
    open(calls);
    const box = await screen.findByLabelText('近义说法');
    fireEvent.change(within(box).getByLabelText('组名'), { target: { value: '大风' } });
    fireEvent.change(within(box).getByLabelText('要加的写法'), { target: { value: '风力，几级风、 刮风' } });
    fireEvent.change(within(box).getByLabelText('理由'), { target: { value: '短' } });
    expect((within(box).getByText('提出') as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(within(box).getByLabelText('理由'), { target: { value: '无人机的知识写的是风力' } });
    fireEvent.click(within(box).getByText('提出'));
    await waitFor(() => {
      const post = calls.find((c) => c.method === 'POST' && c.path === '/admin/pack-synonyms');
      expect(post?.body).toEqual({ name: '大风', words: ['风力', '几级风', '刮风'], includes: [], reason: '无人机的知识写的是风力' });
    });
    fireEvent.change(within(box).getByLabelText('试一句'), { target: { value: '天气不好' } });
    fireEvent.click(within(box).getByText('试'));
    expect(await within(box).findByText('会一起找：变天、下雨、暴雨')).toBeTruthy();
    expect(calls.find((c) => c.path === '/admin/pack-synonyms/expand')?.query).toContain(encodeURIComponent('天气不好'));
  });
});
