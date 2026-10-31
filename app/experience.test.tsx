// KB-080~089 / AGT-080~083 经验变成能被调用的单元——App 这一端（109 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, type Task } from '@platform/core';
import { SubclassesBlock } from './ask';
import { ExperienceToolsBlock } from './experience';
import { RightsScreen } from './rights';

type Call = { method: string; path: string; body: unknown };

function makeClient(routes: Record<string, unknown>, calls: Call[] = []): PlatformClient {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const full = decodeURIComponent(String(url).replace(/^.*\/api\/v1/, ''));
    const path = full.split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: full, body: init?.body ? JSON.parse(init.body) : null });
    const hit = routes[`${method} ${path}`] ?? routes[path];
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ?? []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

function unit(id: number, over: Record<string, unknown> = {}) {
  return {
    id, cluster_id: 1, kind: 'checklist', kind_label: '验收清单', title: `跑腿·同城代取·验收清单${id}`,
    version: 1, status: 'active',
    applicability: { category: '跑腿', cities: [], budget_min_cents: null, budget_max_cents: null,
      exclusions: ['老小区没电梯且要搬大件'] },
    validation: { status: 'unvalidated', uses: 0, closed: 0, reworked: 0, failed: 0 },
    sample_count: 5, scope: 'platform', reuse_license: true, train_license: false,
    created_at: '2026-10-12T00:00:00Z', ...over,
  };
}

const CLUSTER = {
  id: 1, category: '跑腿', label: '跑腿·同城代取', status: 'active', merged_into: null,
  sample_count: 12, price_p50_cents: 20000, price_p90_cents: 35000, duration_p50_days: 0,
  duration_p90_days: 1, priced_samples: 10, outcome_mix: { completed: 10, disputed: 1, cancelled: 1 },
  first_sample_at: null, last_sample_at: null, recent_share: 0.8, few_samples: false, note: '', created_by: 'auto',
};

describe('KB-086 App：子类下的可复用单元', () => {
  it('排除条件跟着单元出现；详情给清单与贡献者', async () => {
    render(<SubclassesBlock client={makeClient({
      '/knowledge/clusters': { semantic: true, model: 'm', items: [CLUSTER] },
      '/knowledge/clusters/1': { ...CLUSTER, consensus_steps: [], dissent: [], dissent_hidden: 0, steps_basis: 0,
        evidence: { shown: [], hidden: 12, note: '个案需双方授权' } },
      '/knowledge/units': [unit(4)],
      '/knowledge/units/4': { ...unit(4), content: { items: ['确认已完成：取件'] }, manifest: {}, est_cost_cents: 0,
        contributors: [{ user_id: 3, nickname: '阿青' }] },
    })} />);
    fireEvent.press(screen.getByText('按子类看'));
    fireEvent.press(await screen.findByText('跑腿·同城代取 ›'));
    expect(await screen.findByText('不适用：老小区没电梯且要搬大件')).toBeTruthy();
    expect(screen.getByText('还没被验证过')).toBeTruthy();
    fireEvent.press(screen.getByText('验收清单 · 跑腿·同城代取·验收清单4'));
    expect(await screen.findByText('☐ 确认已完成：取件')).toBeTruthy();
    expect(screen.getByText(/贡献者：阿青/)).toBeTruthy();
  });
});

describe('AGT-080~083 App：经验工具只出草稿', () => {
  const TASK = { id: 7, title: '代取快递', category: '跑腿' } as unknown as Task;
  const TOOL = unit(9, { kind: 'skill_tool', kind_label: '可执行工具', title: '按验收清单生成验收报告草稿' });

  it('草稿带标签与排除条件；丢弃打到 discard', async () => {
    const calls: Call[] = [];
    render(<ExperienceToolsBlock task={TASK} client={makeClient({
      '/knowledge/units': [TOOL],
      'POST /agent/tools/9/invoke': { invocation_id: 31, draft: true, label: '草稿 · 未经人工确认',
        text: '☐ 确认已完成：取件', exclusions: ['老小区没电梯且要搬大件'], contributors: 10 },
      'POST /agent/tools/invocations/31/discard': { invocation_id: 31, discarded: true },
    }, calls)} />);
    fireEvent.press(await screen.findByText('按验收清单生成验收报告草稿'));
    expect(await screen.findByText('草稿 · 未经人工确认')).toBeTruthy();
    expect(screen.getByText(/不适用的情形：老小区没电梯且要搬大件/)).toBeTruthy();
    expect(calls.find((c) => c.path === '/agent/tools/9/invoke')!.body).toEqual({ task_id: 7 });
    fireEvent.press(screen.getByText('丢弃草稿'));
    await waitFor(() => expect(screen.queryByText('草稿 · 未经人工确认')).toBeNull());
    expect(calls.some((c) => c.method === 'POST' && c.path === '/agent/tools/invocations/31/discard')).toBe(true);
  });

  it('这一类没有经验工具：整块不出现', async () => {
    const calls: Call[] = [];
    render(<ExperienceToolsBlock task={TASK} client={makeClient({ '/knowledge/units': [] }, calls)} />);
    await waitFor(() => expect(calls.length).toBe(1));
    expect(screen.queryByText('用平台经验起草')).toBeNull();
  });
});

describe('KB-080/089 App：经验的两种用途单列', () => {
  it('同意训练打到 experience_train；撤回复用要两步', async () => {
    const calls: Call[] = [];
    const effect = '你参与的任务不再作为经验来源：退出子类统计，用到它的单元转复核';
    render(<RightsScreen client={makeClient({
      '/finance/my-tax': { mode: 'withholding', yearly: [], items: [], disclaimer: 'x' },
      '/legal/agreements': {
        current_version: 'v3', documents: [], sensitive_scopes: [], rights: {},
        data_use_scopes: [
          { key: 'experience_reuse', purpose: '把我参与的任务提炼成别人可复用的经验', granted: true,
            granted_at: '2026-10-01T00:00:00Z', revocable: true, revocation_effect: effect },
          { key: 'experience_train', purpose: '把我参与的任务用于训练模型', granted: false,
            granted_at: null, revocable: true, revocation_effect: '不再用于训练' },
        ],
      },
      'POST /legal/consents/experience_train/grant': { scope: 'experience_train', granted: true, version: 'v3' },
      'POST /legal/consents/experience_reuse/revoke': { scope: 'experience_reuse', revoked: true, effect, applied: ['units_to_review:1'] },
    }, calls)} />);
    expect(await screen.findByText('你参与的任务，能不能成为平台经验')).toBeTruthy();
    expect(screen.getByText(`撤回后：${effect}`)).toBeTruthy();
    fireEvent.press(screen.getByText('授权'));
    await waitFor(() => expect(calls.some((c) => c.path === '/legal/consents/experience_train/grant')).toBe(true));
    fireEvent.press(await screen.findByText('撤回同意'));
    expect(calls.some((c) => c.path.endsWith('/revoke'))).toBe(false);
    fireEvent.press(screen.getByText('确认撤回'));
    await waitFor(() => expect(calls.some((c) => c.path === '/legal/consents/experience_reuse/revoke')).toBe(true));
  });
});
