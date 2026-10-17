// TEAM-066 团队邀请链接在 App 上（147 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { JoinTeamByCode, TeamInviteLinkBlock, inviteToken } from './teamInvites';

type Call = { method: string; path: string; body: unknown };
function makeClient(routes: Record<string, unknown>, calls: Call[]) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    const hit = Object.keys(routes).find((k) => k === `${method} ${path}`) ?? Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : {}) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('TEAM-066 App 上的团队邀请链接', () => {
  it('从整条链接或邀请码里取出令牌', () => {
    expect(inviteToken(' https://x.cn/teams/join/AbC-12_x ')).toBe('AbC-12_x');
    expect(inviteToken('AbC-12_x')).toBe('AbC-12_x');
  });

  it('所有者生成链接交给系统分享，额度按分传', async () => {
    const calls: Call[] = [];
    const share = jest.fn(async () => undefined);
    const client = makeClient({ 'POST /teams/5/invite-links': { id: 1, token: 'tk1', path: '/teams/join/tk1', warning: '', state: 'active',
      spend_limit_cents: 30000, uses: 0, max_uses: 1, expires_at: '2026-10-22T00:00:00Z', created_at: '2026-10-15T00:00:00Z' } }, calls);
    render(<TeamInviteLinkBlock client={client} teamId={5} origin="https://plat.cn" share={share} />);
    fireEvent.changeText(screen.getByLabelText('链接的月度额度'), '300');
    fireEvent.press(screen.getByText('生成并分享邀请链接'));
    await waitFor(() => expect(share).toHaveBeenCalled());
    expect((share.mock.calls[0] as unknown as [{ message: string }])[0].message).toContain('https://plat.cn/teams/join/tk1');
    expect(calls[0].body).toEqual({ spend_limit_cents: 30000 });
  });

  it('没有网页地址时只分享邀请码', async () => {
    const share = jest.fn(async () => undefined);
    const client = makeClient({ 'POST /teams/5/invite-links': { id: 1, token: 'tk1', path: '/teams/join/tk1' } }, []);
    render(<TeamInviteLinkBlock client={client} teamId={5} origin="" share={share} />);
    fireEvent.press(screen.getByText('生成并分享邀请链接'));
    await waitFor(() => expect(share).toHaveBeenCalled());
    expect((share.mock.calls[0] as unknown as [{ message: string }])[0].message).toContain('邀请码 tk1');
  });

  it('被邀请的人粘贴链接：先看清楚是哪个团队、额度多少，再加入', async () => {
    const calls: Call[] = [];
    const onJoined = jest.fn();
    const client = makeClient({
      '/team-invites/tk9': { team_id: 5, team_name: '某某工作室', inviter_nickname: '老板', role: 'member', spend_limit_cents: 30000,
        expires_at: '2026-10-22T00:00:00Z', already_member: false },
      'POST /team-invites/tk9/accept': { team_id: 5, user_id: 9, role: 'member', spend_limit_cents: 30000 },
    }, calls);
    render(<JoinTeamByCode client={client} onJoined={onJoined} />);
    fireEvent.changeText(screen.getByLabelText('邀请链接或邀请码'), 'https://plat.cn/teams/join/tk9');
    fireEvent.press(screen.getByText('看看是哪个团队'));
    expect(await screen.findByText('老板 邀请你加入「某某工作室」，成为普通成员')).toBeTruthy();
    expect(calls.some((c) => c.method === 'POST')).toBe(false);
    fireEvent.press(screen.getByText('加入团队'));
    await waitFor(() => expect(onJoined).toHaveBeenCalled());
    expect(calls.find((c) => c.method === 'POST')?.path).toBe('/team-invites/tk9/accept');
  });
});
