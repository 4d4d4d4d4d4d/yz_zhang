// OUT-052（444 号 spec）App 发单页「按结果计价」：开关打开才出现；请求体与网页同一份；没填完的当场说清、不发请求。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { PublishScreen } from './App';

type Call = { method: string; path: string; body: unknown };
function makeClient(calls: Call[]) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    return { ok: true, status: 200, text: async () => JSON.stringify(method === 'POST' && path === '/tasks' ? { id: 80, title: 'x' } : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}
const posted = (calls: Call[]) => calls.find((c) => c.method === 'POST' && c.path === '/tasks')?.body as Record<string, unknown> | undefined;

function start(calls: Call[], done = jest.fn()) {
  render(<PublishScreen client={makeClient(calls)} onDone={done} category="软件开发" />);
  fireEvent.changeText(screen.getByPlaceholderText(/标题/), '写接口文档');
  fireEvent.press(screen.getAllByText(/^○ /)[0]);
  return done;
}

describe('OUT-052 App 发单页按结果计价', () => {
  it('不开开关：不出现这些输入，请求也不带', async () => {
    const calls: Call[] = [];
    const done = start(calls);
    expect(screen.queryByLabelText('达标关键词')).toBeNull();
    fireEvent.press(screen.getByText('发布（线上任务）'));
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(posted(calls)).not.toHaveProperty('pricing');
    expect(posted(calls)).not.toHaveProperty('acceptance_criteria');
  });

  it('开了开关：没写关键词说清、不发；写了分档带 bonus_tiers 与 pricing=outcome', async () => {
    const calls: Call[] = [];
    const done = start(calls);
    fireEvent(screen.getByLabelText('按结果计价'), 'valueChange', true);
    fireEvent.press(screen.getByText('发布（线上任务）'));
    expect(await screen.findByText(/要写至少一个交付说明里必须写明的关键词/)).toBeTruthy();
    expect(posted(calls)).toBeUndefined();
    fireEvent.changeText(screen.getByLabelText('达标关键词'), '已自测，已部署');
    fireEvent.press(screen.getByText('＋加一档'));
    fireEvent.changeText(screen.getByLabelText('第1档通过几条'), '2');
    fireEvent.changeText(screen.getByLabelText('第1档加付'), '90');
    fireEvent.press(screen.getByText('发布（线上任务）'));
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(posted(calls)).toMatchObject({ pricing: 'outcome', bonus_tiers: [{ min_passed: 2, bonus_cents: 9000 }],
      acceptance_criteria: [{ text: '交付说明写明「已自测」', kind: 'auto', check: { op: 'contains', value: '已自测' } },
        { text: '交付说明写明「已部署」', kind: 'auto', check: { op: 'contains', value: '已部署' } }] });
  });

  it('只写上限：带 bonus_cents', async () => {
    const calls: Call[] = [];
    const done = start(calls);
    fireEvent(screen.getByLabelText('按结果计价'), 'valueChange', true);
    fireEvent.changeText(screen.getByLabelText('达标关键词'), '已自测');
    fireEvent.changeText(screen.getByLabelText('全部达标加付'), '50');
    fireEvent.press(screen.getByText('发布（线上任务）'));
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(posted(calls)).toMatchObject({ pricing: 'outcome', bonus_cents: 5000 });
  });
});
