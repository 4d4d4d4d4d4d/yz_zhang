// CNT-023 / CNT-024 App 上的关注列表与内容流关注按钮（102 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { FollowListScreen } from './spaces';

function makeClient(routes: Record<string, unknown>,
  calls: Array<{ method: string; path: string }> = [],
  errors: Record<string, { status: number; code: string; message: string }> = {}): PlatformClient {
  const fetchImpl = (async (url: string, init?: { method?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path });
    const err = errors[path];
    if (err) return { ok: false, status: err.status, text: async () => JSON.stringify({ detail: { code: err.code, message: err.message } }) };
    const key = Object.keys(routes).find((k) => k === `${method} ${path}`) ?? Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(key ? routes[key] : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

const page = (items: Array<[number, string, boolean | null]>, next: number | null) => ({
  items: items.map(([user_id, nickname, viewer_following]) => ({
    user_id, nickname, followed_at: '2026-10-10T00:00:00Z', viewer_following })),
  next_cursor: next,
});

describe('CNT-023 App 关注列表', () => {
  it('列出关注者；按钮有状态，点了只改这一个人', async () => {
    const calls: Array<{ method: string; path: string }> = [];
    render(<FollowListScreen tab="followers" userId={9} onBack={() => {}}
      client={makeClient({
        '/users/9/followers': page([[11, '粉丝甲', true], [12, '粉丝乙', false]], null),
        'PUT /users/12/follow': { following: true },
      }, calls)} />);
    await screen.findByText('粉丝甲');
    expect(screen.getAllByText('已关注')).toHaveLength(1);
    fireEvent.press(screen.getByText('关注'));
    await waitFor(() => expect(screen.getAllByText('已关注')).toHaveLength(2));
    expect(calls.some((c) => c.method === 'PUT' && c.path === '/users/12/follow')).toBe(true);
  });

  it('对方资料不公开时把服务端的话显示出来', async () => {
    render(<FollowListScreen tab="following" userId={9} onBack={() => {}}
      client={makeClient({}, [], {
        '/users/9/following': { status: 403, code: 'follow_list_private', message: '对方未公开资料，看不到关注列表' },
      })} />);
    await waitFor(() => expect(screen.getByText(/对方未公开资料/)).toBeTruthy());
  });

  it('有下一页时能加载更多', async () => {
    const calls: Array<{ method: string; path: string }> = [];
    render(<FollowListScreen tab="followers" userId={9} onBack={() => {}}
      client={makeClient({ '/users/9/followers': page([[11, '粉丝甲', null]], 30) }, calls)} />);
    fireEvent.press(await screen.findByText('加载更多'));
    await waitFor(() => expect(calls.filter((c) => c.path === '/users/9/followers')).toHaveLength(2));
  });
});
