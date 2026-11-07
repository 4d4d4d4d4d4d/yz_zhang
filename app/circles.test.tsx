// APP-074e（439 号 spec）App 上的圈层：列表、进圈、圈内任务板与动态、发帖、建圈；没加入的看不到圈内内容。
import { readFileSync } from 'fs';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { CirclesScreen } from './circles';

type Call = { method: string; path: string; body: unknown };
type Route = { status?: number; body: unknown };

function makeClient(routes: Record<string, Route>, calls: Call[] = []): PlatformClient {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const full = decodeURIComponent(String(url).replace(/^.*\/api\/v1/, ''));
    const method = init?.method ?? 'GET';
    calls.push({ method, path: full, body: init?.body ? JSON.parse(init.body) : null });
    const hit = routes[`${method} ${full}`] ?? routes[`${method} ${full.split('?')[0]}`] ?? routes[full.split('?')[0]];
    const status = hit?.status ?? 200;
    return { ok: status < 400, status, text: async () => JSON.stringify(hit ? hit.body : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

const base = { description: '', owner_id: 9, skill_tag: '', city: '', min_credit: 0, conversation_id: null, my_role: null };
const MINE = { ...base, id: 1, name: '上海保洁', kind: 'skill', join_policy: 'open', member_count: 12, my_status: 'active', my_role: 'member' };
const OTHER = { ...base, id: 2, name: '徒步爱好者', kind: 'interest', join_policy: 'approval', member_count: 30, my_status: null, min_credit: 80 };
const TASK = { id: 55, title: '开荒保洁两室', budget_cents: 30000, status: 'open' };

describe('APP-074e App 上的圈层', () => {
  it('进已加入的圈：看到圈内任务板、点任务打开详情；发圈内帖', async () => {
    const calls: Call[] = [];
    const opened: number[] = [];
    render(<CirclesScreen onOpenTask={(id) => opened.push(id)} client={makeClient({
      '/circles': { body: [MINE, OTHER] },
      '/circles/1': { body: MINE },
      '/circles/1/feed': { body: [{ id: 3, author_nickname: '王师傅', body: '明天有空' }] },
      '/circles/1/tasks': { body: [TASK] },
      'POST /contents': { body: { id: 4 } },
    }, calls)} />);
    fireEvent.press(await screen.findByText('能力圈 · 上海保洁'));
    expect(await screen.findByText('开荒保洁两室')).toBeTruthy();
    expect(screen.getByText(/王师傅.*明天有空/)).toBeTruthy();
    expect(screen.queryByText('加入圈层')).toBeNull();
    fireEvent.press(screen.getByText('开荒保洁两室'));
    expect(opened).toEqual([55]);
    fireEvent.changeText(screen.getByLabelText('发圈内帖'), ' 周末接单 ');
    fireEvent.press(screen.getByText('发布'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/contents')?.body)
      .toEqual({ body: '周末接单', circle_id: 1, visibility: 'circle' }));
  });

  it('没加入的圈：只看到简介与门槛，「申请加入」后重新拉；圈内内容不去拉；被拒原样说出理由', async () => {
    const calls: Call[] = [];
    render(<CirclesScreen onOpenTask={() => undefined} client={makeClient({
      '/circles': { body: [MINE, OTHER] },
      'POST /circles/2/join': { status: 403, body: { detail: { code: 'circle_credit_too_low', message: '信用分不够 80，暂时不能加入' } } },
    }, calls)} />);
    fireEvent.press(await screen.findByText('兴趣圈 · 徒步爱好者'));
    expect(await screen.findByText('30 位成员 · 信用分 ≥ 80')).toBeTruthy();
    expect(calls.some((c) => c.path.startsWith('/circles/2/'))).toBe(false);
    fireEvent.press(screen.getByText('申请加入'));
    expect(await screen.findByText(/信用分不够 80/)).toBeTruthy();
    expect(calls.some((c) => c.method === 'POST' && c.path === '/circles/2/join')).toBe(true);
  });

  it('建圈：能力圈带技能标签、要审核；名字为空不让建；响应畸形不崩', async () => {
    const calls: Call[] = [];
    render(<CirclesScreen onOpenTask={() => undefined} client={makeClient({
      '/circles': { body: { oops: 1 } },
      'POST /circles': { body: { ...MINE, id: 9 } },
    }, calls)} />);
    expect(await screen.findByText('还没有圈层，可以创建一个')).toBeTruthy();
    fireEvent.press(screen.getByText('＋创建'));
    fireEvent.press(screen.getByText('创建圈层'));
    expect(calls.some((c) => c.method === 'POST')).toBe(false);
    fireEvent.changeText(screen.getByLabelText('圈层名称'), '闵行水电');
    fireEvent.press(screen.getByText('能力圈'));
    fireEvent.changeText(screen.getByLabelText('绑定技能标签'), '水电');
    fireEvent.press(screen.getByText('申请审核'));
    fireEvent.press(screen.getByText('创建圈层'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/circles')?.body)
      .toEqual({ name: '闵行水电', kind: 'skill', skill_tag: '水电', city: '', join_policy: 'approval' }));
  });

  it('挂在「发现」的分段里', () => {
    const src = readFileSync(`${__dirname}/App.tsx`, 'utf8');
    expect(src).toMatch(/\['circles', '圈层'\]/);
    expect(src).toMatch(/seg === 'circles' && <CirclesScreen client=\{client\} onOpenTask=\{onOpenTask\} \/>/);
  });
});
