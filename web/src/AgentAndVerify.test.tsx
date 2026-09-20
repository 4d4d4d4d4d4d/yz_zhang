// CLI-063/064 AI 助理面板与核验台。
//
// 这两个界面此前**根本不存在**：V73/V74 把服务端整条做完了，
// 网页上没有任何入口（57 号 spec）。这里的断言集中在一条上——
// **服务端算好的「为什么不行」必须显示出来**，不能被吞成一个空列表。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = {
  id: 1, phone: '138****0000', nickname: '发布方', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100,
  rating_avg: 0, tasks_completed: 0,
};

const TASK = {
  id: 7, title: '写一篇接口文档', description: '', category: '软件开发', status: 'published',
  budget_cents: 20000, creator_id: 1, executor_id: null, is_remote: true, city: '',
  address_hint: '', address_exact: '', parent_id: null, task_type: 'simple',
  pricing: 'fixed', deposit_status: 'none',
};

function makeClient(routes: Record<string, unknown>, calls: string[] = []): PlatformClient {
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string }) => {
    const u = String(url);
    calls.push(`${init?.method ?? 'GET'} ${u}`);
    // **按整条路径精确匹配**，不用 includes：`/tasks/7` 会把
    // `/tasks/7/applications`、`/tasks/7/progress` 一并吃掉，页面于是拿一个
    // 对象去 .map()，整棵树白屏。没列出来的路径一律返回空数组。
    const path = u.replace(/^.*\/api\/v1/, '').split('?')[0];
    const hit = Object.keys(routes).find((k) => k === path);
    return {
      ok: true, status: 200,
      text: async () => JSON.stringify(hit ? routes[hit] : []),
    };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('AI 助理面板', () => {
  it('CLI-064 不可用的助理显示服务端给的理由，而不是被藏起来', async () => {
    localStorage.setItem('token', 'tok');
    const client = makeClient({
      '/users/me': ME,
      '/tasks/7/eligible-agents': [
        {
          user_id: 9, name: '开发助理', domains: ['软件开发'], max_task_budget_cents: 10000,
          runs_total: 0, runs_succeeded: 0, is_active: true,
          eligible: false, reason: '任务金额超出 AI 助理的承接上限，请交由人工执行',
        },
      ],
      '/agents': [{ user_id: 9, name: '开发助理', domains: ['软件开发'], max_task_budget_cents: 10000, runs_total: 0, runs_succeeded: 0, is_active: true }],
      '/tasks/7': TASK,
    });
    render(
      <MemoryRouter initialEntries={['/tasks/7']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByTestId('agent-reason')).toBeTruthy());
    expect(screen.getByTestId('agent-reason').textContent).toContain('承接上限');
    // 理由摆在那儿，按钮同时是禁用的：说清楚为什么，也别让他白点
    expect((screen.getByText('邀请') as HTMLButtonElement).disabled).toBe(true);
  });

  it('邀请助理打到 agent-apply（此前网页上根本没有这条路）', async () => {
    localStorage.setItem('token', 'tok');
    const calls: string[] = [];
    const client = makeClient({
      '/users/me': ME,
      '/tasks/7/eligible-agents': [
        {
          user_id: 9, name: '开发助理', domains: ['软件开发'], max_task_budget_cents: 50000,
          runs_total: 3, runs_succeeded: 3, is_active: true, eligible: true, reason: '',
        },
      ],
      '/agents': [],
      '/tasks/7': TASK,
    }, calls);
    render(
      <MemoryRouter initialEntries={['/tasks/7']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('邀请')).toBeTruthy());
    fireEvent.click(screen.getByText('邀请'));
    await waitFor(() =>
      expect(calls.some((c) => c.startsWith('POST') && c.includes('/tasks/7/agent-apply?agent_user_id=9'))).toBe(true),
    );
  });

  it('交付闸门与「申请人工核验」入口：闸门文案原样显示', async () => {
    localStorage.setItem('token', 'tok');
    const client = makeClient({
      '/users/me': ME,
      '/agents': [{ user_id: 9, name: '开发助理', domains: ['软件开发'], max_task_budget_cents: 50000, runs_total: 1, runs_succeeded: 0, is_active: true }],
      '/tasks/7/agent-runs': {
        runs: [{
          id: 1, task_id: 7, status: 'escalated', confidence_bps: 4000, output: '半成品',
          criteria_results: [], error: '置信度 40.0% 低于阈值 70.0%',
          moderation_status: 'pass', created_at: null, finished_at: null,
        }],
        delivery_block: 'AI 置信度不足，需人工核验后方可提交交付',
      },
      '/tasks/7': { ...TASK, status: 'in_progress', executor_id: 9 },
    });
    render(
      <MemoryRouter initialEntries={['/tasks/7']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByTestId('delivery-block')).toBeTruthy());
    expect(screen.getByTestId('delivery-block').textContent).toContain('人工核验');
    expect(screen.getByText('申请人工核验')).toBeTruthy();
    // AGT-013 界面必须说清楚置信度是**助理自报的**
    expect(screen.getByText(/自报置信度/)).toBeTruthy();
  });
});

describe('核验台', () => {
  it('CLI-064 不能接的核验单显示资格原因（空列表让人以为是没单）', async () => {
    localStorage.setItem('token', 'tok');
    const client = makeClient({
      '/users/me': ME,
      '/verification-orders': [{
        id: 5, task_id: 7, status: 'open', trigger: 'escalation', fee_cents: 3000,
        payer_id: -1, verifier_id: null, outcome: '', comment: '', revised_output: '',
        criteria_results: [], deadline: null, created_at: null,
        category: '软件开发', task_title: '写一篇接口文档',
        claimable: false, reason: '需有「软件开发」类目的完成记录',
      }],
    });
    render(
      <MemoryRouter initialEntries={['/verify']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByTestId('verify-reason')).toBeTruthy());
    expect(screen.getByTestId('verify-reason').textContent).toContain('完成记录');
    expect((screen.getByText('接下') as HTMLButtonElement).disabled).toBe(true);
    // VER-002 谁付这笔钱要写在单子上
    expect(screen.getByText(/平台付费/)).toBeTruthy();
  });

  it('接单后能看到 AI 产出与判据，并提交结论', async () => {
    localStorage.setItem('token', 'tok');
    const calls: string[] = [];
    const client = makeClient({
      '/users/me': ME,
      '/verification-orders/5/claim': { id: 5, status: 'claimed' },
      '/verification-orders/5/outcome': { outcome: 'approved', unblocked: true, delivered: true },
      '/verification-orders/5': {
        id: 5, task_id: 7, status: 'claimed', trigger: 'escalation', fee_cents: 3000,
        payer_id: -1, verifier_id: 1, outcome: '', comment: '', revised_output: '',
        criteria_results: [], deadline: null, created_at: null,
        task_title: '写一篇接口文档', task_description: '把 REST 接口写清楚',
        category: '软件开发',
        acceptance_criteria: [{ text: '包含鉴权说明', kind: 'auto' }],
        agent_output: '这是 AI 的产出正文', agent_confidence_bps: 4000,
        agent_criteria_results: [{ text: '包含鉴权说明', kind: 'auto', passed: true }],
      },
      '/verification-orders': [{
        id: 5, task_id: 7, status: 'open', trigger: 'escalation', fee_cents: 3000,
        payer_id: -1, verifier_id: null, outcome: '', comment: '', revised_output: '',
        criteria_results: [], deadline: null, created_at: null,
        category: '软件开发', task_title: '写一篇接口文档', claimable: true, reason: '',
      }],
    }, calls);
    render(
      <MemoryRouter initialEntries={['/verify']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('接下')).toBeTruthy());
    fireEvent.click(screen.getByText('接下'));
    await waitFor(() => expect(screen.getByText('这是 AI 的产出正文')).toBeTruthy());
    expect(screen.getByText(/把 REST 接口写清楚/)).toBeTruthy();

    fireEvent.click(screen.getByText('提交结论'));
    await waitFor(() =>
      expect(calls.some((c) => c.startsWith('POST') && c.includes('/verification-orders/5/outcome'))).toBe(true),
    );
  });
});
