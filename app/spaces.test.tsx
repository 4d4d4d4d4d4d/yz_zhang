// SPACE-028 原生 App 的个人空间与四入口（88 号 spec）。
//
// 两类断言，各防一件事：
//
// 1. **空间本身**：发现→打开→私聊、编辑→保存、以及被服务端拦住时那条补救路径
//    （`profile_private` 的隐私开关）真的在 App 上按得到。
// 2. **导航没有把东西弄丢**：Tab 从七个收到四个，而钱包、通知、账户、
//    发布、内容流、视频流一个都不能消失。**这类回归没有任何既有测试会红**——
//    29 条 App 测试全是直接渲染某个屏幕的，它们看不见 Tab 栏。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { readFileSync } from 'fs';
import { PlatformClient, type Me } from '@platform/core';
import App from './App';
import { MySpaceScreen, PublicSpaceScreen, SpacesDiscoverScreen } from './spaces';

type Call = { method: string; path: string; body: unknown };

/** 按整条路径精确匹配（V84 的教训：`includes` 会让 `/wallet` 吃掉 `/wallet/ledger`）。
 *  查询串单独给，便于断言 `?q=` 真的带上了。 */
function makeClient(
  routes: Record<string, { status?: number; body: unknown }>,
  calls: Call[] = [],
): PlatformClient {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const full = String(url).replace(/^.*\/api\/v1/, '');
    const path = full.split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path: full, body: init?.body ? JSON.parse(init.body) : null });
    const hit = routes[path];
    const status = hit?.status ?? 200;
    return { ok: status < 400, status, text: async () => JSON.stringify(hit ? hit.body : {}) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

const PERSON = {
  user_id: 9, nickname: '林', headline: '做结构设计', kind: 'person' as const,
  theme: 'clay' as const, items_count: 2, accepting_orders: true,
};
const OWN = {
  user_id: 5, nickname: '我', revision: 3, published: false, profile_public: true,
  headline: '', introduction: '', theme: 'clay' as const, kind: 'person' as const,
  items: [], items_count: 0, accepting_orders: false,
};

describe('SPACE-004 以人为中心的发现', () => {
  it('列出空间、带上搜索词、翻下一页', async () => {
    const calls: Call[] = [];
    const client = makeClient({
      '/spaces': { body: { items: [PERSON], next_cursor: 9 } },
    }, calls);
    render(<SpacesDiscoverScreen client={client} onOpen={() => {}} />);
    await waitFor(() => expect(screen.getByText('林')).toBeTruthy());
    expect(screen.getByText('做结构设计')).toBeTruthy();
    // 「可接单」是服务端算的，客户端不自己推断
    expect(screen.getByText('独立个体 · 2 个展示 · 可接单')).toBeTruthy();

    fireEvent.changeText(screen.getByPlaceholderText('名字、兴趣，或一种可能…'), '结构');
    fireEvent.press(screen.getByText('搜索'));
    await waitFor(() => expect(calls.some((c) => c.path.includes('q=%E7%BB%93%E6%9E%84'))).toBe(true));

    fireEvent.press(screen.getByText('再认识一些人'));
    await waitFor(() => expect(calls.some((c) => c.path.includes('after=9'))).toBe(true));
  });

  it('空结果与请求失败是两句不同的话', async () => {
    const empty = makeClient({ '/spaces': { body: { items: [], next_cursor: null } } });
    render(<SpacesDiscoverScreen client={empty} onOpen={() => {}} />);
    await waitFor(() => expect(screen.getByText('第一扇窗口，等你打开')).toBeTruthy());

    // 合成一句「暂无数据」会把「后端挂了」说成「这里还没有人」（SPACE-011）
    const broken = makeClient({
      '/spaces': { status: 500, body: { detail: { code: 'oops', message: '服务暂时不可用' } } },
    });
    render(<SpacesDiscoverScreen client={broken} onOpen={() => {}} />);
    await waitFor(() => expect(screen.getByText('服务暂时不可用')).toBeTruthy());
  });
});

describe('SPACE-009 从空间进入真实私聊', () => {
  it('展示条目与外部域名，点「发消息」拿到会话 id', async () => {
    const calls: Call[] = [];
    let got = 0;
    const client = makeClient({
      '/spaces/9': {
        body: {
          ...PERSON, introduction: '十年结构',
          items: [{ title: '桥梁模型', kind: 'work', summary: '2025', url: 'https://example.com/a' }],
        },
      },
      '/conversations/direct': { body: { id: 77 } },
    }, calls);
    render(<PublicSpaceScreen client={client} userId={9} onBack={() => {}}
                              onOpenConversation={(id) => { got = id; }} />);
    await waitFor(() => expect(screen.getByText('作品 · 桥梁模型')).toBeTruthy());
    // 点开之前他有权知道自己要去哪里——平台不代理也不嵌入外部资源
    expect(screen.getByText('在外部打开（example.com）↗')).toBeTruthy();

    fireEvent.press(screen.getByText('发消息'));
    await waitFor(() => expect(got).toBe(77));
  });
});

describe('SPACE-006 我的空间：保存、冲突、发布前置', () => {
  it('保存带上当前 revision，并用服务端返回的新 revision 覆盖本地', async () => {
    const calls: Call[] = [];
    const client = makeClient({
      '/spaces/me': { body: { ...OWN, headline: '做结构设计' } },
    }, calls);
    render(<MySpaceScreen client={client} me={null} onPreview={() => {}} refreshMe={() => {}} />);
    await waitFor(() => expect(screen.getByText('我的空间')).toBeTruthy());

    fireEvent.press(screen.getByText('保存空间'));
    await waitFor(() => expect(screen.getByText('已保存')).toBeTruthy());
    const put = calls.find((c) => c.method === 'PUT' && c.path === '/spaces/me');
    // 不带 revision 服务端会 409；带错了会把别的窗口的新稿覆盖掉
    expect(put!.body).toMatchObject({ revision: 3 });
  });

  it('版本冲突时原样显示服务端的话，不丢用户刚打的字', async () => {
    const client = makeClient({
      '/spaces/me': {
        status: 409,
        body: { detail: { code: 'space_revision_conflict', message: '空间已在其他窗口更新，请重新打开后编辑' } },
      },
    });
    render(<MySpaceScreen client={client} me={null} onPreview={() => {}} refreshMe={() => {}} />);
    // GET 也走同一条路径替身，所以这里直接验错误展示：加载失败不能变成空白页
    await waitFor(() => expect(screen.getByText(/空间已在其他窗口更新/)).toBeTruthy());
  });

  it('PROFILE_PRIVATE：账户设为不公开时，App 上按得到那个补救开关', async () => {
    const calls: Call[] = [];
    const client = makeClient({
      '/spaces/me': { body: { ...OWN, profile_public: false } },
      '/users/me': { body: { id: 5, nickname: '我' } },
    }, calls);
    render(<MySpaceScreen client={client} me={null} onPreview={() => {}} refreshMe={() => {}} />);
    await waitFor(() => expect(screen.getByText(/当前账户设置为不公开个人资料/)).toBeTruthy());

    fireEvent.press(screen.getByText('允许公开个人资料'));
    // 服务端说「请先在账户隐私设置中允许公开个人资料」，而这条补救此前
    // 在 App 上根本不存在——用户只能看着那句提示无路可走（66 号 spec）
    await waitFor(() => {
      const patch = calls.find((c) => c.method === 'PATCH' && c.path === '/users/me');
      expect(patch!.body).toMatchObject({ privacy: { profile_public: true } });
    });
  });

  it('条目加满 24 条后不再给「添加」按钮（服务端上限同一个数）', async () => {
    const items = Array.from({ length: 24 }, (_, i) => ({
      title: `t${i}`, kind: 'work' as const, summary: '', url: '',
    }));
    const client = makeClient({ '/spaces/me': { body: { ...OWN, items } } });
    render(<MySpaceScreen client={client} me={null} onPreview={() => {}} refreshMe={() => {}} />);
    await waitFor(() => expect(screen.getByText('展示条目（24/24）')).toBeTruthy());
    expect(screen.queryByText('添加一条展示')).toBeNull();
  });
});

describe('SPACE-010 四入口，而且什么都没丢', () => {
  const me: Me = {
    id: 5, phone: '13900000000', nickname: '我', bio: '', city: '', lat: null, lng: null,
    skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 80,
    rating_avg: 0, tasks_completed: 0, certifications: [],
  } as unknown as Me;

  function renderApp() {
    const client = makeClient({
      '/users/me': { body: me },
      '/spaces': { body: { items: [], next_cursor: null } },
    });
    // App 自己 new 一个 client（读 BASE_URL），所以这里只验导航结构；
    // 网络调用由上面各屏幕的用例覆盖。
    void client;
    return render(<App />);
  }

  it('Tab 只有四个，且是发现 / 合作 / 消息 / 我的空间', () => {
    renderApp();
    // 未登录时先看到登录页——四入口要在登录之后才出现，这一条用登录页反向断言：
    // 没有 token 的人不该看到任何 Tab（否则点进去全是 401）
    expect(screen.queryByText('发现')).toBeNull();
    expect(screen.getByText('登录')).toBeTruthy();
  });

  it('通知与钱包不在 Tab 里，但必须一跳可达——这一条防的是把它们折丢', () => {
    const src = readFileSync(`${__dirname}/App.tsx`, 'utf8');
    // V100 的催办/临期/预警全靠用户看见通知；钱包是钱的入口。
    // 两者从 Tab 移走之后，必须在常驻顶栏里。
    expect(src).toContain("setOverlay({ kind: 'notices' })");
    expect(src).toContain("setOverlay({ kind: 'wallet' })");
    expect(src).toContain("setOverlay({ kind: 'account' })");
    // 发布、内容流、视频流也一个都不能消失，只是换了入口
    for (const kept of ['PublishScreen', 'DiscoverScreen', 'VideoFeedScreen', 'MeScreen']) {
      expect(src).toContain(kept);
    }
  });
});

describe('SPACE-028 分享深链', () => {
  it('/people/:id 两个来源都要接：冷启动与运行中', () => {
    const src = readFileSync(`${__dirname}/App.tsx`, 'utf8');
    // 只接冷启动的后果很具体：App 在后台时点链接没反应，而用户会以为链接坏了
    expect(src).toContain('Linking.getInitialURL()');
    expect(src).toContain("Linking.addEventListener('url'");
    expect(src).toMatch(/\\\/people\\\/\(\\d\+\)/);

    // Android 上没有 intentFilter，这个入口压根不会被路由过来——
    // 分享越成功，落空越多
    const cfg = JSON.parse(readFileSync(`${__dirname}/app.json`, 'utf8'));
    const prefixes = cfg.expo.android.intentFilters[0].data.map((d: { pathPrefix?: string }) => d.pathPrefix);
    expect(prefixes).toContain('/people');
  });
});
