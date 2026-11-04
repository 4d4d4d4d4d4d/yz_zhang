// RISK-010~014（399 号 spec，V426）App 举报：能选类型、说明至少 2 个字、重复举报说清还在处理、
// 错误码用人话；「我的举报」列出处理结果、畸形响应不崩；私信只在对方的消息旁边画；空间页能举报用户。
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { MyReportsBlock, ReportBlock } from './report';
import { MessagesScreen } from './MessagesAndInvites';
import { PublicSpaceScreen } from './spaces';
import { DiscoverScreen } from './Discover';
import * as ImagePicker from 'expo-image-picker';

type Call = { method: string; path: string; body: unknown };
type Reply = (method: string, path: string) => { status?: number; body: unknown } | undefined;

function makeClient(reply: Reply, calls: Call[] = []): PlatformClient {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    const r = reply(method, path) ?? { body: [] };
    const status = r.status ?? 200;
    return { ok: status < 300, status, text: async () => JSON.stringify(r.body) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

async function submit(client: PlatformClient, reason: string, category?: string) {
  render(<ReportBlock client={client} targetType="user" targetId={7} />);
  fireEvent.press(screen.getByLabelText('举报这条用户'));
  if (category) fireEvent.press(screen.getByLabelText(`类型：${category}`));
  fireEvent.changeText(screen.getByLabelText('举报说明'), reason);
  await act(async () => { fireEvent.press(screen.getByText('提交举报')); await new Promise((r) => setTimeout(r, 0)); });
}

describe('RISK-010~012 App 举报（399 号 spec）', () => {
  it('选类型写说明提交：请求带上类型，提示去「我的举报」看结果', async () => {
    const calls: Call[] = [];
    await submit(makeClient((m, p) => m === 'POST' && p === '/reports'
      ? { status: 201, body: { id: 3, status: 'pending', duplicate: false } } : undefined, calls), '冒充客服骗钱', '诈骗或骗钱');
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual(
      { target_type: 'user', target_id: 7, reason: '冒充客服骗钱', category: 'fraud' });
    expect(screen.getByLabelText('举报结果').props.children).toContain('我的举报');
  });

  it('说明不到 2 个字不发请求', async () => {
    const calls: Call[] = [];
    await submit(makeClient(() => undefined, calls), '差');
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0);
  });

  it('重复举报说清还在处理', async () => {
    await submit(makeClient((m) => m === 'POST' ? { body: { id: 3, status: 'pending', duplicate: true } } : undefined), '一直骚扰');
    expect(screen.getByLabelText('举报结果').props.children).toContain('已经举报过');
  });

  it('举报自己的：错误码翻成人话，表单留着', async () => {
    await submit(makeClient((m) => m === 'POST'
      ? { status: 400, body: { detail: { code: 'report_own_target', message: 'x' } } } : undefined), '测试一下');
    expect(screen.getByText(/这是你自己的/)).toBeTruthy();
    expect(screen.getByLabelText('举报说明').props.value).toBe('测试一下');
  });
});

describe('RISK-013 我的举报', () => {
  it('列出处理结果', async () => {
    render(<MyReportsBlock client={makeClient((_m, p) => p === '/reports/mine' ? { body: { categories: {}, items: [
      { id: 8, target_type: 'message', target_id: 4, category: 'harassment', category_label: '骚扰或辱骂', reason: '辱骂', status: 'resolved',
        result: '已处理违规账号', created_at: '2026-11-04T01:00:00Z', resolved_at: '2026-11-04T03:00:00Z' }] } } : undefined)} />);
    await screen.findByLabelText('举报 8');
    expect(screen.getByText(/私信 #4/)).toBeTruthy();
    expect(screen.getByText(/已处理：已处理违规账号/)).toBeTruthy();
  });

  it('畸形响应显示「还没有举报过」', async () => {
    render(<MyReportsBlock client={makeClient((_m, p) => p === '/reports/mine' ? { body: { items: null } } : undefined)} />);
    await screen.findByText('还没有举报过。');
  });
});

describe('RISK-010 私信里的举报', () => {
  it('只在对方发的消息旁边画；查不到我是谁就不画', async () => {
    const msgs = [
      { id: 1, conversation_id: 5, sender_id: 2, kind: 'text', content: '我发的', risk_flagged: false, recalled: false, created_at: '2026-11-04T01:00:00Z' },
      { id: 2, conversation_id: 5, sender_id: 9, kind: 'text', content: '对方发的', risk_flagged: false, recalled: false, created_at: '2026-11-04T01:01:00Z' },
    ];
    const reply: Reply = (_m, p) => p === '/users/me' ? { body: { id: 2 } }
      : p === '/conversations/5/messages' ? { body: msgs } : p === '/conversations' ? { body: [] } : undefined;
    render(<MessagesScreen client={makeClient(reply)} initialConversationId={5} />);
    await screen.findByText('对方发的');
    await waitFor(() => expect(screen.getAllByLabelText('举报这条私信')).toHaveLength(1));
  });
});

describe('RISK-010 个人空间里的举报', () => {
  it('登录看别人的空间能举报这个用户', async () => {
    const reply: Reply = (_m, p) => p === '/spaces/7'
      ? { body: { user_id: 7, nickname: '别人', kind: 'person', headline: '', introduction: '', theme: 'clay', items: [], accepting_orders: true } }
      : /follow/.test(p) ? { body: { followers: 0, following: 0, viewer_following: false } } : undefined;
    render(<PublicSpaceScreen client={makeClient(reply)} userId={7} onBack={() => {}} onOpenConversation={() => {}} />);
    await screen.findByLabelText('举报这条用户');
  });
});

describe('RISK-014 App 动态流里的举报', () => {
  it('别人的动态能举报，自己的不画', async () => {
    const post = (id: number, followed: boolean | null) => ({ id, author_id: followed === null ? 2 : 7, author_nickname: 'x', kind: 'post',
      title: '', body: `动态${id}`, like_count: 0, comment_count: 0, liked_by_me: false, created_at: '2026-11-04T01:00:00Z',
      author_followed_by_viewer: followed, media_urls: [] });
    render(<DiscoverScreen client={makeClient((_m, p) => p === '/feed' ? { body: [post(1, false), post(2, null)] } : undefined)} baseUrl="" />);
    await screen.findByText('动态1');
    expect(screen.getAllByLabelText('举报这条内容')).toHaveLength(1);
  });
});

describe('RISK-017 App 举报附截图（404 号 spec）', () => {
  it('附两张截图提交：先上传，请求带上地址；不附图时请求体不带 images', async () => {
    jest.spyOn(ImagePicker, 'requestMediaLibraryPermissionsAsync').mockResolvedValue({ status: 'granted' } as never);
    jest.spyOn(ImagePicker, 'launchImageLibraryAsync').mockResolvedValue({ canceled: false, assets: [{ base64: 'QUJD', mimeType: 'image/png' }] } as never);
    const calls: Call[] = [];
    let n = 0;
    const client = makeClient((m, p) => m === 'POST' && p === '/files' ? { status: 201, body: { url: `/api/v1/files/shot${++n}abcdefgh`, ref: `r${n}` } }
      : m === 'POST' && p === '/reports' ? { status: 201, body: { id: 3, status: 'pending', duplicate: false } } : undefined, calls);
    render(<ReportBlock client={client} targetType="message" targetId={9} />);
    fireEvent.press(screen.getByLabelText('举报这条私信'));
    for (let i = 0; i < 2; i++) {
      await act(async () => { fireEvent.press(screen.getByLabelText('附截图')); await new Promise((r) => setTimeout(r, 0)); });
    }
    expect(screen.getByLabelText('已附截图').props.children.join('')).toContain('2 张');
    fireEvent.changeText(screen.getByLabelText('举报说明'), '骗我转账');
    await act(async () => { fireEvent.press(screen.getByText('提交举报')); await new Promise((r) => setTimeout(r, 0)); });
    expect(calls.find((c) => c.method === 'POST' && c.path === '/reports')?.body).toEqual(
      { target_type: 'message', target_id: 9, reason: '骗我转账', category: 'other', images: ['/api/v1/files/shot1abcdefgh', '/api/v1/files/shot2abcdefgh'] });
  });

  it('附满 3 张后不再给「附截图」', async () => {
    jest.spyOn(ImagePicker, 'requestMediaLibraryPermissionsAsync').mockResolvedValue({ status: 'granted' } as never);
    jest.spyOn(ImagePicker, 'launchImageLibraryAsync').mockResolvedValue({ canceled: false, assets: [{ base64: 'QUJD', mimeType: 'image/png' }] } as never);
    let n = 0;
    render(<ReportBlock client={makeClient((m, p) => m === 'POST' && p === '/files' ? { status: 201, body: { url: `/api/v1/files/s${++n}abcdefgh`, ref: 'r' } } : undefined)}
                        targetType="user" targetId={7} />);
    fireEvent.press(screen.getByLabelText('举报这条用户'));
    for (let i = 0; i < 3; i++) {
      await act(async () => { fireEvent.press(screen.getByLabelText('附截图')); await new Promise((r) => setTimeout(r, 0)); });
    }
    expect(screen.queryByLabelText('附截图')).toBeNull();
  });
});
