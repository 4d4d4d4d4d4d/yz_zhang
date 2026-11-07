// KB-080~089 / AGT-080~083 经验变成能被调用的单元（109 号 spec）：网页这一端。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = {
  id: 1, phone: '138****0000', nickname: '我', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: true, credit_score: 100,
  rating_avg: 0, tasks_completed: 0,
};

const TASK = {
  id: 7, title: '代取快递', description: '', category: '跑腿', status: 'published',
  budget_cents: 20000, creator_id: 1, executor_id: null, is_remote: true, city: '杭州',
  address_hint: '', address_exact: '', parent_id: null, task_type: 'service',
  pricing: 'outcome', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none',
};

const VALIDATION = { status: 'unvalidated', uses: 0, closed: 0, reworked: 0, failed: 0 };

function unit(id: number, over: Record<string, unknown> = {}) {
  return {
    id, cluster_id: 1, kind: 'procedure', kind_label: '分解流程', title: `跑腿·同城代取·分解流程${id}`,
    version: 1, status: 'active',
    applicability: { category: '跑腿', cities: [], budget_min_cents: null, budget_max_cents: null,
      exclusions: ['老小区没电梯且要搬大件'] },
    validation: VALIDATION, sample_count: 5, scope: 'platform', reuse_license: true, train_license: false,
    created_at: '2026-10-12T00:00:00Z', ...over,
  };
}

type Call = { method: string; path: string; body: unknown };

function open(path: string, routes: Record<string, unknown>, calls: Call[] = []) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const full = decodeURIComponent(String(url).replace(/^.*\/api\/v1/, ''));
    const p = full.split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: full, body: init?.body ? JSON.parse(init.body) : null });
    // 精确匹配：`/tasks/7` 不许吃掉 `/tasks/7/progress`
    const hit = routes[`${method} ${full}`] ?? routes[`${method} ${p}`] ?? routes[p];
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ?? []) };
  }) as unknown as typeof fetch;
  const client = new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
  render(<MemoryRouter initialEntries={[path]}><AppProvider client={client}><App /></AppProvider></MemoryRouter>);
  return calls;
}

afterEach(() => vi.restoreAllMocks());

describe('KB-086 子类下的可复用单元', () => {
  const CLUSTER = {
    id: 1, category: '跑腿', label: '跑腿·同城代取', status: 'active', merged_into: null,
    sample_count: 12, price_p50_cents: 20000, price_p90_cents: 35000, duration_p50_days: 0,
    duration_p90_days: 1, priced_samples: 10, outcome_mix: { completed: 10, disputed: 1, cancelled: 1 },
    first_sample_at: null, last_sample_at: null, recent_share: 0.8, few_samples: false, note: '', created_by: 'auto',
  };

  it('列出单元时排除条件与验证状态一起出现；详情只列同意了复用的贡献者', async () => {
    open('/ask', {
      '/users/me': ME,
      '/knowledge/clusters': { semantic: true, model: 'm', items: [CLUSTER] },
      '/knowledge/clusters/1': { ...CLUSTER, consensus_steps: [], dissent: [], dissent_hidden: 0, steps_basis: 0,
        evidence: { shown: [], hidden: 12, note: '个案需双方授权' } },
      '/knowledge/units': [unit(4, { validation: { status: 'validated', uses: 6, closed: 5, reworked: 1, failed: 0 } })],
      '/knowledge/units/4': { ...unit(4), content: { steps: [{ title: '接单确认', deliverable: '确认截图' }, { title: '取件' }] },
        manifest: {}, est_cost_cents: 0, contributors: [{ user_id: 3, nickname: '阿青' }] },
    });
    fireEvent.click(await screen.findByRole('button', { name: '按子类看' }));
    fireEvent.click(await screen.findByRole('button', { name: '跑腿·同城代取' }));
    const row = (await screen.findByText(/分解流程 · 跑腿·同城代取·分解流程4/)).closest('[data-unit]')!;
    expect(row.textContent).toMatch(/不适用：老小区没电梯且要搬大件/);
    expect(row.textContent).toMatch(/用过 6 次：做成 5、返工 1、失败 0/);
    fireEvent.click(screen.getByText(/分解流程 · 跑腿·同城代取·分解流程4/));
    expect(await screen.findByText(/贡献者：阿青/)).toBeTruthy();
    expect(screen.getByText('接单确认')).toBeTruthy();
  });
});

describe('AGT-080~083 经验工具', () => {
  const TOOL = unit(9, { kind: 'skill_tool', kind_label: '可执行工具', title: '按验收清单生成验收报告草稿' });
  const DRAFT = {
    invocation_id: 31, draft: true, label: '草稿 · 未经人工确认',
    text: '【草稿 · 未经人工确认】\n☐ 确认已完成：取件', exclusions: ['老小区没电梯且要搬大件'], contributors: 10,
  };

  it('产出带「未经人工确认」标签与排除条件；丢弃打到 discard 并收起草稿', async () => {
    const calls = open('/tasks/7', {
      '/users/me': ME, '/tasks/7': TASK, '/knowledge/units': [TOOL],
      'POST /agent/tools/9/invoke': DRAFT,
      'POST /agent/tools/invocations/31/discard': { invocation_id: 31, discarded: true },
    });
    fireEvent.click(await screen.findByRole('button', { name: '按验收清单生成验收报告草稿' }));
    expect(await screen.findByText('草稿 · 未经人工确认')).toBeTruthy();
    expect(screen.getByText(/不适用的情形：老小区没电梯且要搬大件/)).toBeTruthy();
    const invoke = calls.find((c) => c.method === 'POST' && c.path === '/agent/tools/9/invoke')!;
    expect(invoke.body).toEqual({ task_id: 7 });
    // 列工具时按这一单的类目、只要可执行的那种
    expect(calls.some((c) => c.path.startsWith('/knowledge/units?') && c.path.includes('kind=skill_tool')
      && c.path.includes('category=跑腿'))).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: '丢弃草稿' }));
    await waitFor(() => expect(screen.queryByText('草稿 · 未经人工确认')).toBeNull());
    expect(calls.some((c) => c.method === 'POST' && c.path === '/agent/tools/invocations/31/discard')).toBe(true);
  });

  it('不是这一单的当事人：没有工具入口', async () => {
    const calls = open('/tasks/7', { '/users/me': { ...ME, id: 99 }, '/tasks/7': TASK, '/knowledge/units': [TOOL] });
    expect(await screen.findByText('代取快递')).toBeTruthy();
    expect(screen.queryByText('用平台经验起草')).toBeNull();
    expect(calls.some((c) => c.path.includes('kind=skill_tool'))).toBe(false);
  });
});

describe('KB-080/089 经验的两种用途：单列、各自独立', () => {
  it('复用与训练各一行；撤回前先说后果，撤回打到对应的 scope', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const effect = '你参与的任务不再作为经验来源：退出子类统计，用到它的单元转复核';
    const calls = open('/profile', {
      '/users/me': ME,
      '/legal/agreements': {
        current_version: '2026-09', documents: [], sensitive_scopes: [], rights: {},
        data_use_scopes: [
          { key: 'experience_reuse', purpose: '把我参与的任务提炼成别人可复用的经验', granted: true,
            granted_at: null, revocable: true, revocation_effect: effect },
          { key: 'experience_train', purpose: '把我参与的任务用于训练模型', granted: false,
            granted_at: null, revocable: true, revocation_effect: '不再用于训练' },
        ],
      },
      'POST /legal/consents/experience_reuse/revoke': { scope: 'experience_reuse', revoked: true, effect, applied: ['units_to_review:1'] },
    });
    expect(await screen.findByText('你参与的任务，能不能成为平台经验')).toBeTruthy();
    expect(screen.getByText(effect)).toBeTruthy();
    const buttons = screen.getAllByRole('button', { name: /撤回同意|授权/ });
    expect(buttons.map((b) => b.textContent)).toEqual(['撤回同意', '授权']);
    fireEvent.click(buttons[0]);
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/legal/consents/experience_reuse/revoke')).toBe(true));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining(effect));
  });
});

describe('KB-080/084 运营：蒸馏与复核', () => {
  const OVERVIEW = {
    model: 'm2', semantic: true, active_clusters: 3,
    states: { pending: 0, assigned: 40, undecided: 0, held: 0, excluded: 0, retracted: 0 },
    thresholds: [], held: {},
  };

  it('没写排除条件不能蒸馏；提交时两个授权位都明说', async () => {
    const calls = open('/admin', { '/users/me': ME, '/admin/knowledge/overview': OVERVIEW,
      'POST /admin/knowledge/clusters/3/units': { ...unit(5), content: {}, manifest: {}, est_cost_cents: 0, contributors: [] } });
    const btn = await screen.findByRole('button', { name: '蒸馏单元' }) as HTMLButtonElement;
    fireEvent.change(screen.getByLabelText('从哪个子类蒸馏'), { target: { value: '3' } });
    expect(btn.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('排除条件'), { target: { value: '老小区没电梯\n甲方要当天出图' } });
    expect(btn.disabled).toBe(false);
    fireEvent.click(btn);
    await waitFor(() => expect(calls.some((c) => c.path === '/admin/knowledge/clusters/3/units')).toBe(true));
    const sent = calls.find((c) => c.path === '/admin/knowledge/clusters/3/units')!.body;
    expect(sent).toEqual({ kind: 'procedure', exclusions: ['老小区没电梯', '甲方要当天出图'],
      reuse_license: true, train_license: false });
  });

  it('待复核：重新启用必须写改了什么', async () => {
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValueOnce('').mockReturnValueOnce('第二步改成先约时间');
    const calls = open('/admin', { '/users/me': ME, '/admin/knowledge/overview': OVERVIEW,
      'GET /admin/knowledge/units?status=needs_review': [unit(6, { status: 'needs_review',
        validation: { status: 'needs_review', uses: 4, closed: 1, reworked: 1, failed: 2 } })] });
    const reactivate = await screen.findByRole('button', { name: '重新启用' });
    expect(screen.getByText(/用过 4 次：做成 1、返工 1、失败 2/)).toBeTruthy();
    fireEvent.click(reactivate);
    expect(calls.some((c) => c.method === 'PATCH')).toBe(false);
    fireEvent.click(reactivate);
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH' && c.path === '/admin/knowledge/units/6')).toBe(true));
    expect(calls.find((c) => c.method === 'PATCH')!.body).toEqual({ status: 'active', note: '第二步改成先约时间' });
    expect(promptSpy).toHaveBeenCalledTimes(2);
  });
});
