// AGT-090 App 上的结项报告（132 号 spec）。
import { fireEvent, render, screen } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { CockpitBlock } from './decompose';

function makeClient(routes: Record<string, unknown>) {
  const fetchImpl = (async (url: string) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    return { ok: true, status: 200, text: async () => JSON.stringify(routes[path] ?? []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}
const node = (id: number, title: string) => ({ id, parent_id: 20, title, status: 'completed', status_name: '已完成', budget_cents: 300000,
  is_container: false, depends_on: [], blocked_by: [], executor_id: 5, executor_nickname: '陈设计', deadline: null, overdue: false,
  on_critical_path: false, in_dispute: false });

describe('AGT-090 App 上的结项报告', () => {
  it('全部完成后可看：实付与用时', async () => {
    const client = makeClient({
      '/tasks/20/cockpit': { task_id: 20, title: '公司官网', status: 'completed', progress_pct: 100, steps_total: 2, steps_done: 2,
        budget: { planned_cents: 800000, allocated_cents: 600000, committed_cents: 0, paid_cents: 580000, remaining_cents: 220000 },
        critical_path: [], alerts: [], nodes: [node(21, '需求梳理'), node(22, '页面开发')] },
      '/tasks/20/final-report': { task_id: 20, title: '公司官网', status: 'completed', summary: '共 2 个子任务，完成 2 个', total_cost_cents: 600000,
        planned_budget_cents: 800000, duration_days: 12, children_completed: 2, children_total: 2,
        deliverables: [{ task_id: 21, title: '需求梳理', executor_id: 5, cost_cents: 300000, status: 'completed' }], paid_cents: 580000, ready: true },
    });
    render(<CockpitBlock client={client} taskId={20} />);
    fireEvent.press(await screen.findByText('看结项报告'));
    expect(await screen.findByText('实付（按合约放款）¥5800.00 · 计划 ¥8000.00 · 用时 12 天')).toBeTruthy();
    expect(screen.getByText('• 需求梳理 · ¥3000.00')).toBeTruthy();
  });
});
