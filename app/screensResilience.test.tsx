// APP-093（V213）App 每一屏：响应畸形时不许落到整屏兜底。
//
// 183 号给 App 套了 ScreenBoundary（坏一屏只换说明），但没有逐屏探过：钱包、工作台、个人空间等拿到 {} / null
// 会不会整屏换成「这一页没加载出来」。列表接口的畸形响应在共享 SDK 里收成空表；对象响应由各屏用 hasLists 看一眼，
// 不像样只让那一块说明原因。这里把主框架能进的每一屏 × 四种畸形响应都渲染一遍。
import { Component, type ReactNode } from 'react';
import { render } from '@testing-library/react-native';
import { PlatformClient, type Me } from '@platform/core';
import { WalletScreen } from './App';
import { MessagesScreen } from './MessagesAndInvites';
import { MySpaceScreen, PublicSpaceScreen } from './spaces';
import { SUB_SCREEN_LABEL, SubScreenHost, type SubScreen } from './TeamCoopDev';

/** 与 ScreenBoundary 一样接住渲染错误；接住了就记下哪一处，断言时报出来（失败信息直接指到出错的组件）。 */
class Probe extends Component<{ children: ReactNode; onCatch: (msg: string) => void }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(e: Error, info: { componentStack?: string | null }) {
    this.props.onCatch(`${e.message}\n${(info.componentStack ?? '').split('\n').slice(0, 4).join('\n')}`);
  }
  render() { return this.state.failed ? null : this.props.children; }
}

const ME = { id: 1, nickname: '探针用户' } as unknown as Me;
const BODIES: Array<[string, unknown]> = [['{}', {}], ['null', null], ['[]', []], ['"x"', 'x']];

function clientReturning(body: unknown) {
  const fetchImpl = (async () => ({ ok: true, status: 200, text: async () => JSON.stringify(body) })) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

const SCREENS: Array<[string, (c: PlatformClient) => JSX.Element]> = [
  ['钱包', (c) => <WalletScreen client={c} />],
  ['我的空间', (c) => <MySpaceScreen client={c} me={ME} refreshMe={() => {}} onPreview={() => {}} />],
  ['别人的空间', (c) => <PublicSpaceScreen client={c} userId={9} onBack={() => {}} onOpenConversation={() => {}} />],
  ['消息', (c) => <MessagesScreen client={c} initialConversationId={null} />],
  ...(Object.keys(SUB_SCREEN_LABEL) as SubScreen[]).map((k): [string, (c: PlatformClient) => JSX.Element] =>
    [`子页 ${k}`, (c) => <SubScreenHost client={c} screen={k} onBack={() => {}} />]),
];

describe('APP-093 App 每一屏：响应畸形时不落到整屏兜底', () => {
  beforeEach(() => jest.spyOn(console, 'error').mockImplementation(() => {}));
  afterEach(() => jest.restoreAllMocks());

  for (const [name, make] of SCREENS)
    for (const [label, body] of BODIES)
      it(`${name} · 响应 ${label}`, async () => {
        let caught = '';
        render(<Probe onCatch={(m) => { caught = m; }}>{make(clientReturning(body))}</Probe>);
        await new Promise((r) => setTimeout(r, 30));   // 让各块的请求都回来、都画一遍
        if (caught) throw new Error(`整屏落到兜底：${caught}`);
      });

  it('子页清单与主框架一致（新加的子页自动进探针）', () => {
    expect(Object.keys(SUB_SCREEN_LABEL).length).toBeGreaterThanOrEqual(22);
  });
});
