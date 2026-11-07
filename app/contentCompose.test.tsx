// APP-074f（441 号 spec）App 上发动态、草稿、点赞、评论。
import { readFileSync } from 'fs';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, type ContentItem } from '@platform/core';
import { ComposeBlock, ContentActions } from './contentCompose';

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

const ITEM = { id: 5, title: '', body: '今天修好了一扇窗', like_count: 2, comment_count: 1, liked_by_me: false,
  author_id: 9, author_nickname: '王师傅', author_followed_by_viewer: false, media_urls: [] } as unknown as ContentItem;

describe('APP-074f 发动态与草稿', () => {
  it('发布去掉首尾空格、发完通知外面刷新；存草稿带 publish:false；空的不让发', async () => {
    const calls: Call[] = [];
    let refreshed = 0;
    render(<ComposeBlock onPublished={() => { refreshed += 1; }} client={makeClient({
      '/contents/mine': { body: [] }, 'POST /contents': { body: { id: 1 } },
    }, calls)} />);
    fireEvent.press(await screen.findByText('发布'));
    expect(calls.some((c) => c.method === 'POST')).toBe(false);
    fireEvent.changeText(screen.getByLabelText('动态内容'), '  周末可以接单  ');
    fireEvent.press(screen.getByText('发布'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ body: '周末可以接单' }));
    await waitFor(() => expect(refreshed).toBe(1));
    fireEvent.changeText(screen.getByLabelText('动态内容'), '先存着');
    fireEvent.press(screen.getByText('存草稿'));
    await waitFor(() => expect(calls.filter((c) => c.method === 'POST')[1]?.body).toEqual({ body: '先存着', publish: false }));
    expect(refreshed).toBe(1);
  });

  it('草稿：列出来、改了保存走 PATCH、单独发布；服务端的理由原样说出来', async () => {
    const calls: Call[] = [];
    render(<ComposeBlock client={makeClient({
      '/contents/mine': { body: [{ ...ITEM, id: 7, body: '草稿一', status: 'draft' }] },
      'PATCH /contents/7': { body: { id: 7 } },
      'POST /contents/7/publish': { status: 409, body: { detail: { code: 'already_published', message: '已经是发布状态' } } },
    }, calls)} />);
    expect(await screen.findByText('我的草稿（1）')).toBeTruthy();
    fireEvent.press(screen.getByText('改'));
    expect(screen.getByText('改草稿')).toBeTruthy();
    fireEvent.changeText(screen.getByLabelText('动态内容'), '草稿一改过');
    fireEvent.press(screen.getByText('保存草稿'));
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ body: '草稿一改过' }));
    await screen.findByText('草稿已保存');
    fireEvent.press(screen.getAllByText('发布')[1]);       // 第一个是发动态的「发布」，第二个是草稿那一行的
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/contents/7/publish')).toBe(true));
    expect(await screen.findByText('已经是发布状态')).toBeTruthy();
  });
});

describe('APP-074f 点赞与评论', () => {
  it('点赞以服务端返回的为准；评论展开才拉、发送后计数加一并重拉', async () => {
    const calls: Call[] = [];
    render(<ContentActions item={ITEM} client={makeClient({
      'POST /contents/5/like': { body: { liked: true, like_count: 10 } },   // 期间别人也点了：以服务端的总数为准
      '/contents/5/comments': { body: [{ id: 1, author_nickname: '李姐', body: '好手艺' }] },
      'POST /contents/5/comments': { body: { id: 2 } },
    }, calls)} />);
    fireEvent.press(screen.getByText('赞 2'));
    expect(await screen.findByText('已赞 10')).toBeTruthy();
    expect(calls.some((c) => c.path === '/contents/5/comments')).toBe(false);
    fireEvent.press(screen.getByText('评论 1'));
    expect(await screen.findByText(/李姐.*好手艺/)).toBeTruthy();
    fireEvent.changeText(screen.getByLabelText('写评论'), ' 想约你 ');
    fireEvent.press(screen.getByText('发送'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/contents/5/comments')?.body)
      .toEqual({ body: '想约你', reply_to_id: null }));
    await waitFor(() => expect(calls.filter((c) => c.method === 'GET' && c.path === '/contents/5/comments').length).toBe(2));
    fireEvent.press(screen.getByText('收起评论'));
    expect(screen.getByText('评论 2')).toBeTruthy();
    await new Promise((r) => setTimeout(r, 20));
    expect(calls.filter((c) => c.method === 'GET' && c.path === '/contents/5/comments').length).toBe(2);   // 收起不拉
  });

  it('挂在 App 的内容流里：顶部发动态，每张卡片下面点赞评论', () => {
    const src = readFileSync(`${__dirname}/Discover.tsx`, 'utf8');
    expect(src).toMatch(/<ComposeBlock client=\{client\} onPublished=\{\(\) => void load\(\)\} \/>/);
    expect(src).toMatch(/<ContentActions client=\{client\} item=\{item\} \/>/);
  });
});
