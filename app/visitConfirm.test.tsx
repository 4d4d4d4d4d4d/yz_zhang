// SCN-192（317 号 spec）App 上发单人对上门回报表态：对得上就确认，对不上写清哪里不对再提交；接单人只看结果。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, type Task } from '@platform/core';
import { VisitsBlock } from './visits';

type Call = { method: string; path: string; body: unknown };
const TASK = { id: 70, creator_id: 9, executor_id: 2, title: '上门收废品', status: 'in_progress', is_remote: false,
  visits_planned: 1, visit_checklist: ['分类', '当面称'] } as unknown as Task;
const V = (extra = {}) => ({ task_id: 70, planned: 1, checklist: ['分类', '当面称'], reported: 1, missed_total: 0,
  visits: [{ n: 1, id: 5, created_at: '2030-01-05T02:00:00Z', done: ['分类', '当面称'], missed: [], note: '纸箱 12.4 斤', images: [], at_site_m: null, ...extra }] });

function client(visits: unknown, after: unknown, calls: Call[]) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    return { ok: true, status: 200, text: async () => JSON.stringify(method === 'GET' ? visits : after) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('SCN-192 App 上门回报的确认与异议', () => {
  it('发单人：对得上；有异议要写清再提交', async () => {
    const calls: Call[] = [];
    render(<VisitsBlock client={client(V(), V({ confirmed_at: '2030-01-05T03:00:00Z' }), calls)} task={TASK} isExecutor={false} />);
    fireEvent.press(await screen.findByText('对得上'));
    expect(await screen.findByText(/发单人已确认/)).toBeTruthy();
    fireEvent.press(screen.getByText('有异议'));
    fireEvent.press(screen.getByText('提交异议'));
    expect(await screen.findByText('写清哪里对不上（至少两个字）')).toBeTruthy();
    expect(calls.some((c) => c.path === '/tasks/70/visits/5/object')).toBe(false);
    fireEvent.changeText(screen.getByLabelText('哪里对不上'), ' 实际不到 12 斤 ');
    fireEvent.press(screen.getByText('提交异议'));
    await waitFor(() => expect(calls.find((c) => c.path === '/tasks/70/visits/5/object')?.body).toEqual({ reason: '实际不到 12 斤' }));
  });

  it('接单人：看得到异议，没有表态的按钮', async () => {
    render(<VisitsBlock client={client(V({ objection: '实际不到 12 斤' }), null, [])} task={TASK} isExecutor />);
    expect(await screen.findByText('有异议：实际不到 12 斤')).toBeTruthy();
    expect(screen.queryByText('对得上')).toBeNull();
    expect(screen.queryByText('有异议')).toBeNull();
  });
});
