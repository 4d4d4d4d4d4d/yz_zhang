// KB-070~076 经验子类：用户侧「按子类看」与运营面（108 号 spec）。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = {
  id: 1, phone: '138****0000', nickname: '我', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: true, credit_score: 100,
  rating_avg: 0, tasks_completed: 0,
};

function cluster(id: number, over: Record<string, unknown> = {}) {
  return {
    id, category: '跑腿', label: `跑腿·同城代取${id}`, status: 'active', merged_into: null,
    sample_count: 12, price_p50_cents: 20000, price_p90_cents: 35000, duration_p50_days: 0,
    duration_p90_days: 1, priced_samples: 10, outcome_mix: { completed: 10, disputed: 1, cancelled: 1 },
    first_sample_at: '2026-06-01T00:00:00Z', last_sample_at: '2026-10-01T00:00:00Z', recent_share: 0.8,
    few_samples: false, note: '', created_by: 'auto', ...over,
  };
}

type Call = { method: string; path: string; body: unknown };

function open(path: string, routes: Record<string, unknown>, calls: Call[] = []) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    // SDK 会给类目名做 URL 编码；按解码后的路径匹配
    const p = decodeURIComponent(String(url).replace(/^.*\/api\/v1/, ''));
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : null });
    const hit = routes[`${method} ${p.split('?')[0]}`] ?? routes[p.split('?')[0]];
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ?? []) };
  }) as unknown as typeof fetch;
  const client = new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
  render(<MemoryRouter initialEntries={[path]}><AppProvider client={client}><App /></AppProvider></MemoryRouter>);
  return calls;
}

describe('KB-073/074 按子类看', () => {
  it('每个子类带样本量、分布、纠纷与取消；样本少的不给价并说明', async () => {
    open('/ask', { '/users/me': ME, '/knowledge/clusters': { semantic: true, model: 'm', items: [
      cluster(1), cluster(2, { sample_count: 2, few_samples: true, note: '样本过少（2 个），仅供参考' }),
    ] } });
    fireEvent.click(await screen.findByRole('button', { name: '按子类看' }));
    const one = await screen.findByText(/12 个样本/);
    expect(one.textContent).toMatch(/价格中位 ¥200\.00/);
    expect(one.textContent).toMatch(/有纠纷 1/);
    expect(one.textContent).toMatch(/取消 1/);
    const few = (await screen.findByText(/^2 个样本/)).closest('[data-cluster]')!;
    expect(few.textContent).not.toMatch(/价格中位/);
    expect(within(few as HTMLElement).getByText(/样本过少/)).toBeTruthy();
  });

  it('详情给共识与分歧；只出现一次的做法只数不展示；个案不展示', async () => {
    open('/ask', { '/users/me': ME, '/knowledge/clusters': { semantic: true, model: 'm', items: [cluster(1)] },
      '/knowledge/clusters/1': { ...cluster(1), consensus_steps: [{ title: '接单确认', count: 8 }],
        dissent: [{ steps: ['约时间', '上门代办'], count: 2 }], dissent_hidden: 3, steps_basis: 10,
        evidence: { shown: [], hidden: 12, note: '个案需双方授权后才能展示' } } });
    fireEvent.click(await screen.findByRole('button', { name: '按子类看' }));
    fireEvent.click(await screen.findByRole('button', { name: '跑腿·同城代取1' }));
    expect(await screen.findByText(/接单确认/)).toBeTruthy();
    expect(screen.getByText(/约时间 → 上门代办/)).toBeTruthy();
    expect(screen.getByText(/另有 3 种只出现过一次的做法/)).toBeTruthy();
    expect(screen.getByText(/个案需双方授权/)).toBeTruthy();
  });

  it('不是语义检索时说出来；没有子类时说清不是出错', async () => {
    open('/ask', { '/users/me': ME, '/knowledge/clusters': { semantic: false, model: 'local-bow', items: [] } });
    fireEvent.click(await screen.findByRole('button', { name: '按子类看' }));
    expect(await screen.findByText(/还没有子类/)).toBeTruthy();
  });
});

describe('KB-070/071 运营面', () => {
  const OVERVIEW = {
    model: 'm2', semantic: true, active_clusters: 3,
    states: { pending: 0, assigned: 40, undecided: 1, held: 1, excluded: 2, retracted: 0 },
    thresholds: [{ category: '保洁', tau_merge: 0.9, tau_near: 0.7, embedding_model: 'm1', stale: true,
      labeled_pairs: 12, errors: 1, calibrated_at: '2026-10-01T00:00:00Z' }],
    held: { no_threshold: 1, model_mismatch: 0 },
  };
  const ROWS = [
    { card_id: 7, category: '跑腿', city: '上海', title: '跑腿·上海', outcome: 'completed', state: 'undecided',
      hint: { nearest_id: 3, nearest_label: '跑腿·同城代取', similarity: 0.9, why: '像又不够像' }, created_at: null },
    { card_id: 8, category: '搬家', city: '杭州', title: '搬家·杭州', outcome: 'completed', state: 'held',
      hint: { reason: 'no_threshold', note: '「搬家」还没有标定归并阈值' }, created_at: null },
  ];

  it('旧模型标的阈值会被拒：大声说出来；待定区可并入最像的子类', async () => {
    const calls = open('/admin', { '/users/me': ME, '/admin/knowledge/overview': OVERVIEW,
      '/admin/knowledge/undecided': ROWS, 'POST /admin/knowledge/cards/7/assign': cluster(3) });
    expect((await screen.findByText(/阈值是用旧模型标定的/)).textContent).toMatch(/保洁/);
    const row = (await screen.findByText('跑腿·上海')).closest('[data-card]') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: /并入「跑腿·同城代取」/ }));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ cluster_id: 3, new_label: '' }));
    expect(screen.getByText(/还没有标定归并阈值/)).toBeTruthy();
  });

  it('标定：逐对标完才能提交，提交的是标注本身', async () => {
    const pair = (i: number) => ({ a: { card_id: i, city: '杭州', title: `跑腿·杭州${i}`, outcome: 'completed', price_actual_cents: 100, duration_days: 0 },
      b: { card_id: i + 100, city: '上海', title: `跑腿·上海${i}`, outcome: 'completed', price_actual_cents: 100, duration_days: 0 }, similarity: 0.5 });
    const calls = open('/admin', { '/users/me': ME, '/admin/knowledge/overview': OVERVIEW, '/admin/knowledge/undecided': [],
      '/admin/knowledge/thresholds/跑腿/pairs': [pair(1), pair(2)],
      'POST /admin/knowledge/thresholds/跑腿/calibrate': { category: '跑腿', tau_merge: 0.9, tau_near: 0.7,
        embedding_model: 'm2', labeled_pairs: 2, errors: 0, calibrated_at: null } });
    fireEvent.change(await screen.findByLabelText('要标定的大类'), { target: { value: '跑腿' } });
    fireEvent.click(screen.getByRole('button', { name: '取一组样本对' }));
    const p0 = (await screen.findByText(/跑腿·杭州1/)).closest('[data-pair]') as HTMLElement;
    const submit = screen.getByRole('button', { name: '用这些标注标定' }) as HTMLButtonElement;
    fireEvent.click(within(p0).getByRole('button', { name: '是一回事' }));
    expect(submit.disabled).toBe(true);
    const p1 = screen.getByText(/跑腿·杭州2/).closest('[data-pair]') as HTMLElement;
    fireEvent.click(within(p1).getByRole('button', { name: '不是' }));
    expect(submit.disabled).toBe(false);
    fireEvent.click(submit);
    await waitFor(() => expect(calls.find((c) => c.path.endsWith('/calibrate'))?.body).toEqual({
      pairs: [{ a: 1, b: 101, same: true }, { a: 2, b: 102, same: false }],
    }));
    expect(await screen.findByText(/「跑腿」已标定/)).toBeTruthy();
  });
});
