// PACK-100 服务包在 App 上的行为（123 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { PacksScreen } from './packs';

type Call = { method: string; path: string; body?: unknown };
const CARD = {
  key: 'collab-basics', version: 2, title: '平台协作入门', segment: 'general', summary: '一页讲清托管、验收、纠纷',
  pains: ['不知道钱什么时候付'], enabled: true, enabled_version: 1, upgrade_available: true, active_users: 3, published_at: '',
  assets: {
    assistants: [{ key: 'collab-advisor', name: '协作顾问', persona: '熟悉平台规则', inputs: [], outputs: [], forbidden: [], tools: [],
      human_gates: ['付款、收款、转账、托管'] }],
    methods: [{ key: 'm', name: '接单前确认清单', steps: 5 }], knowledge: [], routines: [], task_templates: [],
  },
};

function makeClient(routes: Record<string, unknown>, calls: Call[]) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : undefined });
    const hit = Object.keys(routes).find((k) => k === `${method} ${path}`) ?? Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('PACK-100 App 上的服务包', () => {
  it('有新版本时可以升级；问助手专家，答不了给发单入口', async () => {
    const calls: Call[] = [];
    const onPublish = jest.fn();
    const client = makeClient({
      '/packs': [CARD],
      'POST /packs/collab-basics/enable': { ...CARD, enabled_version: 2, upgrade_available: false, installed: { methods: 1, notes: 5, routines: 1 } },
      'POST /packs/collab-basics/assistants/collab-advisor/ask': { assistant: '协作顾问', gates: [], gate_notice: '', refused: false,
        answer: '这个问题包里的资料和你的笔记都没有覆盖到。', citations: [],
        remedy: { action: 'publish_task', category: '法律咨询', label: '发布一单「法律咨询」，请专业的人来做' } },
    }, calls);
    render(<PacksScreen client={client} onPublish={onPublish} />);
    fireEvent.press(await screen.findByText('平台协作入门（已启用）'));
    fireEvent.press(await screen.findByText('升级（只补新增的）'));
    expect(await screen.findByText('已启用：1 份做法、5 条知识、1 个定时提醒')).toBeTruthy();
    fireEvent.changeText(screen.getByPlaceholderText('问协作顾问'), '对方不付尾款');
    fireEvent.press(screen.getByText('问'));
    fireEvent.press(await screen.findByText('发布一单「法律咨询」，请专业的人来做'));
    expect(onPublish).toHaveBeenCalledWith('法律咨询');
    await waitFor(() => expect(calls.find((c) => c.path === '/packs/collab-basics/assistants/collab-advisor/ask')?.body).toEqual({ q: '对方不付尾款' }));
  });

  it('停用与反馈', async () => {
    const calls: Call[] = [];
    const client = makeClient({ '/packs': [{ ...CARD, upgrade_available: false }],
      'POST /packs/collab-basics/disable': { disabled: true, removed: 0, kept_modified: 0 }, 'POST /packs/collab-basics/feedback': { recorded: true } }, calls);
    render(<PacksScreen client={client} />);
    fireEvent.press(await screen.findByText('平台协作入门（已启用）'));
    fireEvent.press(await screen.findByText('停用（装进来的留着）'));
    await waitFor(() => expect(calls.find((c) => c.path === '/packs/collab-basics/disable')?.body).toEqual({ remove_copies: false }));
    fireEvent.press(screen.getByText('有用'));
    await waitFor(() => expect(calls.find((c) => c.path === '/packs/collab-basics/feedback')?.body).toEqual({ helpful: true }));
  });
});
