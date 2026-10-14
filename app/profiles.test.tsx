// PROF-100 任务画像与能力画像在 App 上的行为（126 号 spec）。
import { render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { CapabilityScreen, DraftHints, TaskProfileBlock } from './profiles';

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

describe('PROF-100 App 上的画像', () => {
  it('发布时提示缺什么与预算位置', async () => {
    const calls: Call[] = [];
    const client = makeClient({ 'POST /profiles/task-draft': { category: '跑腿', mode: 'remote', declared_skills: [], inferred_skills: [], size: 'small',
      price: { sample_size: 3, p50_cents: 5000, min_cents: 3000, max_cents: 8000, position: 'below_median' }, risks: [],
      completeness: 0.5, checks: [{ key: 'deadline', ok: false, hint: '给一个截止时间' }] } }, calls);
    render(<DraftHints client={client} draft={{ title: '帮忙取快递', category: '跑腿', budget_cents: 3500, is_remote: true }} delayMs={0} />);
    expect(await screen.findByText('说明完整度 50%')).toBeTruthy();
    expect(screen.getByText('预算低于同类成交中位（中位 ¥50.00）')).toBeTruthy();
    expect(screen.getByText('· 给一个截止时间')).toBeTruthy();
    await waitFor(() => expect(calls.find((c) => c.path === '/profiles/task-draft')?.body).toMatchObject({ title: '帮忙取快递', budget_cents: 3500 }));
  });

  it('取不到画像时不显示，不挡发布', async () => {
    const client = makeClient({}, []);
    render(<DraftHints client={client} draft={{ title: 'x' }} delayMs={0} />);
    await waitFor(() => expect(screen.queryByText(/说明完整度/)).toBeNull());
  });

  it('任务详情：这单的画像写出风险与技能', async () => {
    const client = makeClient({ '/tasks/7/profile': { task_id: 7, category: '跑腿', mode: 'onsite', declared_skills: [], inferred_skills: ['驾驶'],
      size: 'medium', price: { sample_size: 0, p50_cents: null, min_cents: null, max_cents: null, position: 'unknown' },
      risks: [{ kind: 'advance', text: '需要垫付：金额与凭证提前说清' }], completeness: 0.7, checks: [] } }, []);
    render(<TaskProfileBlock client={client} taskId={7} />);
    expect(await screen.findByText('⚠ 需要垫付：金额与凭证提前说清')).toBeTruthy();
    expect(screen.getByText(/线下 · 技能：驾驶 · 说明完整度 70%/)).toBeTruthy();
  });

  it('我的能力画像：自述与佐证分开', async () => {
    const client = makeClient({ '/users/me/capability': { user_id: 2, tasks_completed: 2, categories: [{ category: '保洁', completed: 2, rating_avg: 5 }],
      skills: [{ skill: '收纳', evidenced: false }], certifications: [], on_time_rate: null, rework_rate: null, reply_hours_median: null,
      has_weekly_slots: false, limited_capacity: false, note: '', disputes: 0 } }, []);
    render(<CapabilityScreen client={client} />);
    expect(await screen.findByText('· 保洁：完成 2 单，平均 5 星')).toBeTruthy();
    expect(screen.getByText('技能：收纳（自述）')).toBeTruthy();
    expect(screen.getByText(/准时交付 样本不足/)).toBeTruthy();
  });
});
