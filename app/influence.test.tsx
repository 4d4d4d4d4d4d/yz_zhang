// INF-100 影响力与专家等级在 App 上的行为（127 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, influenceLeaf, sha256Hex } from '@platform/core';
import { InfluenceBlock, InfluenceScreen } from './influence';

type Call = { method: string; path: string; query: string; body?: unknown };
function makeClient(routes: Record<string, unknown>, calls: Call[], fail?: (c: Call) => { status: number; body: unknown } | null) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const [path, query = ''] = String(url).replace(/^.*\/api\/v1/, '').split('?');
    const call = { method: init?.method ?? 'GET', path, query, body: init?.body ? JSON.parse(init.body) : undefined };
    calls.push(call);
    const f = fail?.(call);
    if (f) return { ok: false, status: f.status, text: async () => JSON.stringify(f.body) };
    const hit = Object.keys(routes).find((k) => k === `${call.method} ${path}`) ?? Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}
const VOUCH = {
  id: 5, voucher_id: 2, voucher_nickname: '我', subject_id: 9, subject_nickname: '林', category: '保洁', task_id: null,
  stake: 20, status: 'active', note: '', created_at: '2026-10-13T08:00:00Z', resolved_at: null,
};
// 按服务端同样的算法真算出叶子与树根：App 要能自己验算
const LEAF = influenceLeaf(2, '保洁', 64);
const SIB = 'ef'.repeat(32);
const ROOT = sha256Hex(LEAF < SIB ? LEAF + SIB : SIB + LEAF);
const MINE = {
  categories: [{ category: '保洁', points: 64, tier: 'skilled', tier_name: '熟手', completed: 6, rating_avg: 4.8, locked: 20, available: 12,
    gaps: ['升到「专家」：影响力还差 56 点'] }],
  events: [{ id: 1, category: '保洁', kind: 'restore', points: 30, reason: '申诉改判，恢复此前的罚没', created_at: '2026-10-12T08:00:00Z' }],
  vouches_given: [VOUCH], vouches_received: [], rules: '只能靠在平台上做成事挣；不能转让',
};

describe('INF-100 App 上的影响力', () => {
  it('我的等级与还差什么、明细、排行；撤回担保；查看证明', async () => {
    const calls: Call[] = [];
    const client = makeClient({
      '/influence/me': MINE, 'DELETE /influence/vouches/5': { withdrawn: true },
      '/influence/leaderboard': { category: '保洁', items: [{ user_id: 7, nickname: '老王', tier: 'expert', tier_name: '专家', points: 180, completed: 25 }] },
      '/users/me': { id: 2 },
      '/influence/me/proof': { snapshot: { id: 3, taken_at: '2026-10-13T00:00:00Z', merkle_root: ROOT, leaves: 40, anchor_seq: 17 },
        items: [{ category: '保洁', points: 64, leaf: LEAF, path: [SIB], verified: true }] },
    }, calls);
    render(<InfluenceScreen client={client} />);
    expect(await screen.findByText('保洁 · 熟手 · 影响力 64 · 完成 6 单')).toBeTruthy();
    expect(screen.getByText('担保占用 20 · 还能担保 12')).toBeTruthy();
    expect(screen.getByText('升到「专家」：影响力还差 56 点')).toBeTruthy();
    expect(await screen.findByText('1. 老王 · 专家 · 影响力 180')).toBeTruthy();
    expect(screen.getByText(/\+30 申诉恢复/)).toBeTruthy();
    fireEvent.press(screen.getByLabelText('撤回对 林 的担保'));
    expect(await screen.findByText('已撤回对 林 的担保')).toBeTruthy();
    expect(calls.some((c) => c.method === 'DELETE' && c.path === '/influence/vouches/5')).toBe(true);
    fireEvent.press(screen.getByText('查看我的证明'));
    expect(await screen.findByText('保洁：64 · 验证通过 · 本机验算通过')).toBeTruthy();
    expect(screen.getByText('快照 #3 · 40 条 · 存证序号 17')).toBeTruthy();
  });

  it('别人空间：看到等级与担保汇总；为他担保，被拒绝时说清为什么', async () => {
    const calls: Call[] = [];
    let first = true;
    const client = makeClient({
      '/users/9/influence': { user_id: 9, categories: [{ category: '保洁', points: 40, tier: 'skilled', tier_name: '熟手', completed: 4, rating_avg: null }],
        vouched: [{ category: '保洁', vouchers: 2, stake: 30 }] },
      'POST /influence/vouches': { ...VOUCH, stake: 5 },
    }, calls, (c) => {
      if (c.method === 'POST' && first) { first = false; return { status: 409, body: { detail: { code: 'influence_vouch_tier', message: 'x' } } }; }
      return null;
    });
    render(<InfluenceBlock client={client} userId={9} />);
    expect(await screen.findByText('保洁：熟手 · 影响力 40 · 完成 4 单')).toBeTruthy();
    expect(screen.getByText('2 人以 30 点为他的「保洁」作保')).toBeTruthy();
    fireEvent.press(screen.getByText('为他担保'));
    fireEvent.changeText(screen.getByLabelText('担保额'), '5');
    fireEvent.press(screen.getByText('确认担保'));
    expect(await screen.findByText(/做到熟手以上/)).toBeTruthy();
    fireEvent.press(screen.getByText('确认担保'));
    expect(await screen.findByText('已用 5 点「保洁」影响力为他担保')).toBeTruthy();
    await waitFor(() => expect(calls.filter((c) => c.method === 'POST').pop()?.body).toEqual({ subject_id: 9, category: '保洁', task_id: null, stake: 5, note: '' }));
  });

  it('取不到（老服务端）就不显示', async () => {
    const client = makeClient({}, [], () => ({ status: 404, body: { detail: 'Not Found' } }));
    render(<InfluenceBlock client={client} userId={9} />);
    await waitFor(() => expect(screen.queryByText('影响力')).toBeNull());
  });
});
