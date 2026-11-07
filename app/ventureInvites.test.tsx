// COOP-060 合作体邀请、加入、分配记录在 App 上（142 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { DistributionHistoryBlock, InviteMemberBlock, VentureInvitesBlock } from './ventureInvites';

type Call = { method: string; path: string; body?: unknown };
function makeClient(routes: Record<string, unknown>, calls: Call[]) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : undefined });
    const hit = Object.keys(routes).find((k) => k === `${method} ${path}`) ?? Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}
const INVITE = { venture_id: 31, name: '社区咖啡', purpose: '周末快闪', inviter_id: 2, inviter_nickname: '阿青', expires_at: '2026-10-20T00:00:00Z', risk_disclosure_version: 'v2' };
const DOC = { title: '风险揭示书', version: 'v2', points: ['可能血本无归', '份额会被稀释'], text: '全文' };

describe('COOP-060 App 上的合作体邀请', () => {
  it('读完风险揭示书、勾上「已阅读」才能签署加入；用的是服务端给的版本号', async () => {
    const calls: Call[] = [];
    const onJoined = jest.fn();
    const client = makeClient({ '/ventures/invitations': [INVITE], '/ventures/risk-disclosure': DOC,
      'POST /ventures/31/members': { venture_id: 31, user_id: 5, role: 'member' } }, calls);
    render(<VentureInvitesBlock client={client} onJoined={onJoined} />);
    expect(await screen.findByText('阿青 邀请你加入 · 周末快闪 · 2026-10-20 前有效')).toBeTruthy();
    fireEvent.press(screen.getByText('读风险揭示书后加入'));
    expect(await screen.findByText('1. 可能血本无归')).toBeTruthy();
    fireEvent.press(screen.getByText('签署并加入'));
    expect(calls.some((c) => c.method === 'POST')).toBe(false);
    fireEvent(screen.getByLabelText('我已阅读并理解上述风险'), 'valueChange', true);
    fireEvent.press(screen.getByText('签署并加入'));
    await waitFor(() => expect(onJoined).toHaveBeenCalled());
    expect(calls.find((c) => c.method === 'POST')).toEqual({ method: 'POST', path: '/ventures/31/members', body: { risk_disclosure_version: 'v2' } });
  });

  it('可以拒绝', async () => {
    const calls: Call[] = [];
    const client = makeClient({ '/ventures/invitations': [INVITE], '/ventures/risk-disclosure': DOC,
      'POST /ventures/31/invitations/decline': { venture_id: 31, status: 'declined' } }, calls);
    render(<VentureInvitesBlock client={client} onJoined={() => undefined} />);
    fireEvent.press(await screen.findByText('拒绝'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/ventures/31/invitations/decline')).toBe(true));
  });

  it('没有邀请就不显示这一块', async () => {
    const calls: Call[] = [];
    render(<VentureInvitesBlock client={makeClient({ '/ventures/invitations': [] }, calls)} onJoined={() => undefined} />);
    await waitFor(() => expect(calls.some((c) => c.path === '/ventures/invitations')).toBe(true));
    expect(screen.queryByLabelText('我收到的邀请')).toBeNull();
  });

  it('成员能按编号邀请、能看分配记录（含当时的份额快照）', async () => {
    const calls: Call[] = [];
    const client = makeClient({ 'POST /ventures/31/invitations': { invited: 9, venture_id: 31, risk_disclosure_version: 'v2' },
      '/ventures/31/invitations/sent': [{ invitee_id: 8, invitee_nickname: '小林', status: 'expired', created_at: '2026-10-10T00:00:00Z',
        expires_at: '2026-10-17T00:00:00Z', accepted_at: null }],
      '/ventures/31/distributions': [{ id: 1, total_cents: 30000, memo: '首月', created_at: '2026-10-10T00:00:00Z',
        share_snapshot: [{ user_id: 2, valued_cents: 1, share_bps: 6000 }, { user_id: 5, valued_cents: 1, share_bps: 4000 }] }] }, calls);
    render(<><InviteMemberBlock client={client} ventureId={31} /><DistributionHistoryBlock client={client} ventureId={31} /></>);
    expect(await screen.findByText('2026-10-10 · 共 ¥300.00 · 首月（按当时份额：#2 60.00%、#5 40.00%）')).toBeTruthy();
    expect(await screen.findByText('· 小林：已过期（可以再邀一次）')).toBeTruthy();   // COOP-062 我发出的邀请
    fireEvent.changeText(screen.getByLabelText('被邀请人编号'), '9');
    fireEvent.press(screen.getByText('发出邀请'));
    expect(await screen.findByText('已邀请 #9')).toBeTruthy();
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ user_id: 9 });
  });
});
