// COOP-060 合作体邀请、加入、分配记录在网页上（142 号 spec）。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 5, phone: '138****0005', nickname: '我', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0 };
const RISK = { version: 'rd-2026-02', title: '早期合作风险揭示书', points: ['可能没有任何回报；'], text: '全文' };
const INVITE = { venture_id: 31, name: '社区咖啡', purpose: '周末快闪', inviter_id: 2, inviter_nickname: '阿青',
  expires_at: '2026-10-20T00:00:00Z', risk_disclosure_version: 'rd-2026-02' };
type Call = { method: string; path: string; body?: unknown };

function open(routes: Record<string, unknown>, calls: Call[] = []) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const key = Object.keys(routes).find((k) => k === `${method} ${p}`) ?? Object.keys(routes).find((k) => k === p);
    return { ok: true, status: 200, text: async () => JSON.stringify(key ? routes[key] : []) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/ventures']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
  return calls;
}

describe('COOP-060 合作体邀请', () => {
  it('收到的邀请：整篇读风险揭示书、勾上已阅读才能加入，签的是服务端给的版本', async () => {
    const calls = open({ '/users/me': ME, '/ventures/risk-disclosure': RISK, '/ventures/mine': [], '/ventures/invitations': [INVITE],
      'POST /ventures/31/members': { venture_id: 31, user_id: 5, role: 'member' } });
    const box = await screen.findByLabelText('我收到的邀请');
    expect(box.textContent).toContain('阿青 邀请你加入');
    fireEvent.click(screen.getByText('读风险揭示书后加入'));
    const join = await screen.findByText('签署并加入') as HTMLButtonElement;
    expect(join.disabled).toBe(true);
    fireEvent.click(screen.getAllByLabelText(/我已阅读并理解上述风险/)[0]);
    fireEvent.click(screen.getByText('签署并加入'));
    await screen.findByText('已加入「社区咖啡」');
    expect(calls.find((c) => c.method === 'POST')).toEqual({ method: 'POST', path: '/ventures/31/members', body: { risk_disclosure_version: 'rd-2026-02' } });
  });

  it('拒绝邀请', async () => {
    const calls = open({ '/users/me': ME, '/ventures/risk-disclosure': RISK, '/ventures/mine': [], '/ventures/invitations': [INVITE],
      'POST /ventures/31/invitations/decline': { venture_id: 31, status: 'declined' } });
    fireEvent.click(await screen.findByText('拒绝'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/ventures/31/invitations/decline')).toBe(true));
  });

  it('合作体详情：邀请成员与分配记录', async () => {
    const calls = open({ '/users/me': ME, '/ventures/risk-disclosure': RISK, '/ventures/invitations': [],
      '/ventures/mine': [{ id: 31, name: '社区咖啡', purpose: '', category: '', status: 'active', founder_id: 5, created_at: null, role: 'founder' }],
      '/ventures/31': { id: 31, name: '社区咖啡', purpose: '', category: '', status: 'active', founder_id: 5, created_at: null, members: [], shares: [], realized_funds_cents: 0 },
      '/ventures/31/shares': { shares: [], total_bps: 0, basis: '份额按已确认贡献计算' },
      '/ventures/31/compliance-path': { documents: [], registrations: [], notices: [], disclaimer: '不是法律意见' },
      '/ventures/31/distributions': [{ id: 1, total_cents: 30000, memo: '首月', created_at: '2026-10-10T00:00:00Z',
        share_snapshot: [{ user_id: 5, valued_cents: 1, share_bps: 10000 }] }],
      'POST /ventures/31/invitations': { invited: 9, venture_id: 31, risk_disclosure_version: 'rd-2026-02' },
      // COOP-062（220 号 spec）我发出的邀请
      '/ventures/31/invitations/sent': [{ invitee_id: 8, invitee_nickname: '小林', status: 'declined', created_at: '2026-10-10T00:00:00Z',
        expires_at: '2026-10-17T00:00:00Z', accepted_at: null }] });
    fireEvent.click(await screen.findByText('打开'));
    expect((await screen.findByLabelText('我发出的邀请')).textContent).toContain('小林：已拒绝');
    const hist = await screen.findByLabelText('分配记录');
    await waitFor(() => expect(hist.textContent).toContain('共 ¥300.00 · 首月'));
    expect(hist.textContent).toContain('#5 100.00%');
    fireEvent.change(screen.getByLabelText('被邀请人编号'), { target: { value: '9' } });
    fireEvent.click(screen.getByText('发出邀请'));
    await screen.findByText('已邀请 #9');
    expect(calls.find((c) => c.method === 'POST' && c.path === '/ventures/31/invitations')?.body).toEqual({ user_id: 9 });
    await waitFor(() => expect(calls.filter((c) => c.path === '/ventures/31/invitations/sent').length).toBe(2));   // 发出后刷新
  });
});
