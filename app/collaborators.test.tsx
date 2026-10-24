// APP-079 找合作者——App 这一端（110 号 spec）。
//
// 钉的是三件容易做错的事：推荐要带理由、不可用的助理要原样说出服务端的理由
// （按钮同时点不动）、置信度要写明是助理自报的。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, type Task } from '@platform/core';
import { AgentBlock, RecommendationsBlock } from './collaborators';

type Call = { method: string; path: string; body: unknown };

function makeClient(routes: Record<string, unknown>, calls: Call[] = []): PlatformClient {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const full = decodeURIComponent(String(url).replace(/^.*\/api\/v1/, ''));
    const path = full.split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: full, body: init?.body ? JSON.parse(init.body) : null });
    // 精确匹配：`/tasks/7` 不许吃掉 `/tasks/7/agent-runs`
    const hit = routes[`${method} ${path}`] ?? routes[path];
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ?? []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

const TASK = {
  id: 7, title: '写一篇接口文档', category: '软件开发', status: 'published', budget_cents: 20000,
  creator_id: 1, executor_id: null, is_remote: true,
} as unknown as Task;

const AGENT = {
  user_id: 9, name: '开发助理', domains: ['软件开发'], max_task_budget_cents: 10000,
  runs_total: 3, runs_succeeded: 2, is_active: true,
};

describe('MATCH-001/002 App：AI 推荐人选', () => {
  it('每个推荐带理由与匹配度；邀约打到 invitations 并标已邀约', async () => {
    const calls: Call[] = [];
    render(<RecommendationsBlock task={TASK} client={makeClient({
      '/tasks/7/recommendations': [
        { user_id: 5, nickname: '小李', score: 0.87, credit_score: 98, rating_avg: 4.9, skills: ['接口文档'],
          reasons: ['技能匹配：接口文档', '信用 98'] },
      ],
      'POST /tasks/7/invitations': { id: 1, status: 'pending' },
    }, calls)} />);
    expect(await screen.findByText('技能匹配：接口文档 · 信用 98')).toBeTruthy();
    expect(screen.getByText(/匹配 87%/)).toBeTruthy();
    fireEvent.press(screen.getByText('邀约 小李'));
    expect(await screen.findByText('已邀约')).toBeTruthy();
    expect(calls.find((c) => c.method === 'POST')!.body).toEqual({ user_id: 5, message: '诚邀接单' });
  });

  it('没有推荐：整块不出现', async () => {
    const calls: Call[] = [];
    render(<RecommendationsBlock task={TASK} client={makeClient({}, calls)} />);
    await waitFor(() => expect(calls.length).toBe(1));
    expect(screen.queryByText('AI 推荐人选')).toBeNull();
  });
});

describe('CLI-063/064 App：AI 助理', () => {
  it('不可用的助理原样显示服务端给的理由，而且邀请点不动', async () => {
    const calls: Call[] = [];
    render(<AgentBlock task={TASK} onChanged={() => undefined} client={makeClient({
      '/agents': [AGENT],
      '/tasks/7/eligible-agents': [{ ...AGENT, eligible: false, reason: '任务金额超出 AI 助理的承接上限，请交由人工执行' }],
    }, calls)} />);
    expect(await screen.findByTestId('agent-reason')).toBeTruthy();
    expect(screen.getByText('任务金额超出 AI 助理的承接上限，请交由人工执行')).toBeTruthy();
    fireEvent.press(screen.getByText('邀请 开发助理'));
    expect(calls.some((c) => c.path.includes('/agent-apply'))).toBe(false);
  });

  it('可用的助理：邀请打到 agent-apply', async () => {
    const calls: Call[] = [];
    render(<AgentBlock task={TASK} onChanged={() => undefined} client={makeClient({
      '/agents': [AGENT],
      '/tasks/7/eligible-agents': [{ ...AGENT, eligible: true, reason: '' }],
      'POST /tasks/7/agent-apply': { id: 3, status: 'pending', agent_user_id: 9 },
    }, calls)} />);
    fireEvent.press(await screen.findByText('邀请 开发助理'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/tasks/7/agent-apply?agent_user_id=9')).toBe(true));
    expect(await screen.findByText('已邀请 开发助理')).toBeTruthy();
  });

  it('需到场的任务：不出现助理面板（AGT-010）', async () => {
    const calls: Call[] = [];
    render(<AgentBlock task={{ ...TASK, is_remote: false } as Task} onChanged={() => undefined}
                       client={makeClient({ '/agents': [AGENT] }, calls)} />);
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    expect(screen.queryByText('AI 助理')).toBeNull();
  });

  it('助理在执行：置信度写明是自报的；交付被拦下时给人工核验入口', async () => {
    const calls: Call[] = [];
    const running = { ...TASK, status: 'in_progress', executor_id: 9 } as Task;
    render(<AgentBlock task={running} onChanged={() => undefined} client={makeClient({
      '/agents': [AGENT],
      '/tasks/7/agent-runs': {
        runs: [{ id: 1, task_id: 7, status: 'escalated', confidence_bps: 6200, output: '初稿……',
          criteria_results: [{ text: '包含全部接口', kind: 'auto', passed: false }], error: '',
          moderation_status: 'pass', created_at: null, finished_at: null }],
        delivery_block: '平台判据未通过：包含全部接口',
      },
      'POST /tasks/7/verification': { id: 2, status: 'open' },
    }, calls)} />);
    expect(await screen.findByText('待人工核验 · 助理自报置信度 62.0%')).toBeTruthy();
    expect(screen.getByText('✗ 包含全部接口')).toBeTruthy();
    expect(screen.getByTestId('delivery-block')).toBeTruthy();
    fireEvent.press(screen.getByText('申请人工核验'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/tasks/7/verification')).toBe(true));
    expect(screen.getByText('重新执行')).toBeTruthy();
  });
});
