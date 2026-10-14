// INF-100 影响力与专家等级（127 号 spec）：我的等级与还差什么、担保与撤回、排行、快照证明；别人空间里的影响力与担保。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { InfluenceCard } from './Profiles';
import { AppProvider } from './store';

const ME = {
  id: 2, phone: '138****0002', nickname: '我', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100,
  rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2',
};
type Call = { method: string; path: string; query: string; body?: unknown };
const VOUCH = {
  id: 5, voucher_id: 2, voucher_nickname: '我', subject_id: 9, subject_nickname: '林', category: '保洁', task_id: null,
  stake: 20, status: 'active', note: '', created_at: '2026-10-13T08:00:00Z', resolved_at: null,
};
const MINE = {
  categories: [{ category: '保洁', points: 64, tier: 'skilled', tier_name: '熟手', completed: 6, rating_avg: 4.8,
    locked: 20, available: 12, gaps: ['升到「专家」：影响力还差 56 点；还要再完成 4 单'] }],
  events: [{ id: 1, category: '保洁', kind: 'slash_dispute', points: -10, reason: '「两居室」纠纷败诉（拿到 20%）', created_at: '2026-10-12T08:00:00Z' }],
  vouches_given: [VOUCH],
  vouches_received: [],
  rules: '只能靠在平台上做成事挣；不能转让',
};
const PROOF = {
  snapshot: { id: 3, taken_at: '2026-10-13T00:00:00Z', merkle_root: 'ab'.repeat(32), leaves: 40, anchor_seq: 17 },
  items: [{ category: '保洁', points: 64, leaf: 'cd'.repeat(32), path: ['ef'.repeat(32)], verified: true }],
};

function open(path: string, routes: Record<string, unknown>, calls: Call[] = []) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const [p0, query = ''] = String(url).replace(/^.*\/api\/v1/, '').split('?');
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p0, query, body: init?.body ? JSON.parse(init.body) : undefined });
    const key = Object.keys(routes).find((k) => k === `${method} ${p0}`) ?? Object.keys(routes).find((k) => k === p0);
    return { ok: true, status: 200, text: async () => JSON.stringify(key ? routes[key] : (p0 === '/users/me' ? ME : [])) };
  }) as unknown as typeof fetch;
  return { calls, client: new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl }) };
}

describe('INF-100 影响力', () => {
  it('我的等级、还差什么、担保占用与可用、变动明细；撤回担保；排行；快照证明', async () => {
    const { calls, client } = open('/influence', {
      '/influence/me': MINE, 'DELETE /influence/vouches/5': { withdrawn: true }, '/influence/me/proof': PROOF,
      '/influence/leaderboard': { category: '保洁', items: [{ user_id: 7, nickname: '老王', tier: 'expert', tier_name: '专家', points: 180, completed: 25 }] },
    });
    render(<MemoryRouter initialEntries={['/influence']}><AppProvider client={client}><App /></AppProvider></MemoryRouter>);
    const tiers = await screen.findByLabelText('我的等级');
    await waitFor(() => expect(tiers.textContent).toContain('保洁 · 熟手'));
    expect(tiers.textContent).toContain('担保占用 20 · 还能担保 12');
    expect(tiers.textContent).toContain('升到「专家」：影响力还差 56 点');
    expect(screen.getByLabelText('明细').textContent).toContain('-10 纠纷败诉');
    await waitFor(() => expect(screen.getByLabelText('排行').textContent).toContain('老王 · 专家 · 影响力 180'));
    expect(calls.find((c) => c.path === '/influence/leaderboard')?.query).toBe(`category=${encodeURIComponent('保洁')}`);
    fireEvent.click(screen.getByRole('button', { name: '撤回' }));
    await screen.findByText('已撤回对 林 的担保');
    expect(calls.some((c) => c.method === 'DELETE' && c.path === '/influence/vouches/5')).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: '查看我的证明' }));
    const proof = await screen.findByText(/验证通过/);
    expect(proof.textContent).toContain('保洁：64');
    expect(screen.getByLabelText('存证').textContent).toContain('存证序号 17');
  });

  it('别人的空间：看到等级与担保汇总，熟手以上可以为他担保；服务端拒绝时说清为什么', async () => {
    let fail = true;
    const routes: Record<string, unknown> = {
      '/users/9/influence': { user_id: 9, categories: [{ category: '保洁', points: 40, tier: 'skilled', tier_name: '熟手', completed: 4, rating_avg: null }],
        vouched: [{ category: '保洁', vouchers: 2, stake: 30 }] },
    };
    const { calls } = open('/', routes);
    const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
      const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
      calls.push({ method: init?.method ?? 'GET', path: p, query: '', body: init?.body ? JSON.parse(init.body) : undefined });
      if (init?.method === 'POST' && fail) {
        fail = false;
        return { ok: false, status: 409, text: async () => JSON.stringify({ detail: { code: 'influence_stake_exceeds', message: 'x' } }) };
      }
      if (init?.method === 'POST') return { ok: true, status: 201, text: async () => JSON.stringify({ ...VOUCH, stake: 5 }) };
      return { ok: true, status: 200, text: async () => JSON.stringify(routes[p] ?? []) };
    }) as unknown as typeof fetch;
    render(<MemoryRouter><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}>
      <InfluenceCard userId={9} isMe={false} /></AppProvider></MemoryRouter>);
    const card = await screen.findByLabelText('影响力');
    expect(card.textContent).toContain('保洁：熟手 · 影响力 40 · 完成 4 单');
    expect(card.textContent).toContain('2 人以 30 点为他的「保洁」作保');
    fireEvent.click(screen.getByRole('button', { name: '为他担保' }));
    fireEvent.change(screen.getByLabelText('担保额'), { target: { value: '50' } });
    fireEvent.click(screen.getByRole('button', { name: '确认担保' }));
    expect((await screen.findByText(/担保额超出可用额度/)).textContent).toContain('不超过你在这个类目影响力的一半');
    fireEvent.change(screen.getByLabelText('担保额'), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: '确认担保' }));
    await screen.findByText('已用 5 点「保洁」影响力为他担保');
    expect(calls.filter((c) => c.method === 'POST').pop()?.body).toEqual({ subject_id: 9, category: '保洁', task_id: null, stake: 5, note: '' });
  });

  it('自己的空间且还没有影响力：不显示这一块；接口不存在（老服务端）也不带崩', async () => {
    const fetchImpl = vi.fn(async () => ({ ok: false, status: 404, text: async () => '{"detail":"Not Found"}' })) as unknown as typeof fetch;
    const { container } = render(<MemoryRouter><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}>
      <InfluenceCard userId={2} isMe /></AppProvider></MemoryRouter>);
    await waitFor(() => expect(fetchImpl).toHaveBeenCalled());
    expect(container.querySelector('[aria-label="影响力"]')).toBeNull();
  });
});
