// SCN-157（281 号 spec）App 空间编辑：给作品填「来自平台上的哪一单」，保存时带上 task_id；不填不带；公开页标注。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { MySpaceScreen, PublicSpaceScreen } from './spaces';

type Call = { method: string; path: string; body: unknown };
function makeClient(routes: Record<string, unknown>, calls: Call[] = []) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path, body: init?.body ? JSON.parse(init.body) : null });
    return { ok: true, status: 200, text: async () => JSON.stringify(routes[path] ?? {}) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}
const OWN = {
  user_id: 5, nickname: '我', revision: 3, published: false, profile_public: true, headline: '整理收纳', introduction: '',
  theme: 'clay' as const, kind: 'person' as const, accepting_orders: false, items_count: 2,
  items: [{ title: '衣橱整理前后', kind: 'work', summary: '', url: '' }, { title: '厨房', kind: 'work', summary: '', url: '' }],
};

describe('SCN-157 App 空间关联任务', () => {
  it('第一条填任务编号、第二条不填：请求里只有第一条带 task_id', async () => {
    const calls: Call[] = [];
    render(<MySpaceScreen client={makeClient({ '/spaces/me': OWN }, calls)} me={null} onPreview={() => {}} refreshMe={() => {}} />);
    fireEvent.changeText(await screen.findByLabelText('第 1 条关联任务'), '60');
    fireEvent.changeText(screen.getByLabelText('第 2 条关联任务'), '1.5');   // 不是整数编号就不带
    fireEvent.press(screen.getByText('保存空间'));
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true));
    const items = (calls.find((c) => c.method === 'PUT')!.body as { items: Array<Record<string, unknown>> }).items;
    expect(items[0].task_id).toBe(60);
    expect('task_id' in items[1] && items[1].task_id !== undefined).toBe(false);
  });

  it('公开页：关联了任务的作品标「平台上做过的单」', async () => {
    const pub = { user_id: 9, nickname: '林', headline: '整理收纳', theme: 'clay', kind: 'person', items_count: 1, accepting_orders: true,
      introduction: '', items: [{ title: '衣橱整理前后', kind: 'work', summary: '', url: '', task_id: 60 }] };
    render(<PublicSpaceScreen client={makeClient({ '/spaces/9': pub })} userId={9} onBack={() => {}} onOpenConversation={() => {}} />);
    await waitFor(() => expect(screen.getByText('作品 · 衣橱整理前后')).toBeTruthy());
    expect(screen.getByText('平台上做过的单 · 委托方已同意展示')).toBeTruthy();
  });
});
