// APP-075 我的权益：代扣明细、单独同意、数据主体权利（87 / 29 / 52 号 spec）。
//
// 这三样都是**法定权利**，而它们此前只有网页有。执行方主要在手机上——
// 「只能去电脑上撤回同意」不是一种可行使的权利。
//
// 这几条测试钉的是「入口在、而且按下去做对事」，特别是两件容易做错的：
// 服务端的免责声明与撤回后果**必须原样显示**，而撤回这个破坏性动作
// 不能一下点中。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { Share } from 'react-native';
import { RightsScreen } from './rights';

type Call = { method: string; path: string; body: unknown };

/** 按整条路径精确匹配（V84 的教训：`includes` 会让 `/wallet` 吃掉 `/wallet/ledger`）。 */
function makeClient(
  routes: Record<string, { status?: number; body: unknown }>,
  calls: Call[] = [],
): PlatformClient {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path, body: init?.body ? JSON.parse(init.body) : null });
    const hit = routes[path];
    const status = hit?.status ?? 200;
    return { ok: status < 400, status, text: async () => JSON.stringify(hit ? hit.body : {}) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

const TAX = {
  mode: 'withholding',
  yearly: [{ year: 2026, income_cents: 460000, withheld_cents: 73600, count: 1 }],
  items: [],
  disclaimer: '本明细为平台代扣记录，不是税务机关出具的完税证明。',
};
const SCOPE = {
  key: 'id_document', purpose: '证件信息用于实名与责任主体确认',
  granted: true, granted_at: '2026-01-01T00:00:00Z', revocable: true,
  revocation_effect: '实名能力失效，接单、提现与资金操作一并停止',
};
const AGREEMENTS = {
  current_version: 'v3', documents: [],
  sensitive_scopes: [SCOPE],
  rights: { export: '导出我的数据', erase: '注销账号并删除数据' },
};

describe('TAX-021 代扣明细：执行方报税的唯一凭据', () => {
  it('按年列出收入与代扣，并原样显示服务端的免责声明', async () => {
    const client = makeClient({
      '/finance/my-tax': { body: TAX },
      '/legal/agreements': { body: AGREEMENTS },
    });
    render(<RightsScreen client={client} />);
    await waitFor(() => expect(screen.getByText('2026 年')).toBeTruthy());
    // 金额走共享 SDK 的 `fmtYuan`（无千分位），客户端不另写一份格式化——
    // LEDG-004 立过这条：第二份格式化迟早和账单对不上
    expect(screen.getByText(/收入 ¥4600\.00 · 已代扣 ¥736\.00 · 1 笔/)).toBeTruthy();
    // 平台出具的是代扣明细、不是完税证明——这句话的法律含义不容客户端改写
    expect(screen.getByText(TAX.disclaimer)).toBeTruthy();
  });

  it('没有记录时说清为什么是空的，而不是只写「暂无数据」', async () => {
    const client = makeClient({
      '/finance/my-tax': { body: { ...TAX, yearly: [] } },
      '/legal/agreements': { body: AGREEMENTS },
    });
    render(<RightsScreen client={client} />);
    await waitFor(() => expect(screen.getByText(/有收入并完成放款后会出现在这里/)).toBeTruthy());
  });

  it('代扣明细读不到，不该让同意项也看不见', async () => {
    // 合成一次 Promise.all + 一个 catch 会让一侧的故障把另一侧一起带走
    const client = makeClient({
      '/finance/my-tax': { status: 500, body: { detail: { code: 'x', message: '税务服务异常' } } },
      '/legal/agreements': { body: AGREEMENTS },
    });
    render(<RightsScreen client={client} />);
    await waitFor(() => expect(screen.getByText(SCOPE.purpose)).toBeTruthy());
    expect(screen.getByText('税务服务异常')).toBeTruthy();
  });
});

describe('LAW-031 单独同意：撤回是权利，但不能一下点中', () => {
  it('撤回后果在他点撤回之前就在屏幕上', async () => {
    const client = makeClient({
      '/finance/my-tax': { body: TAX },
      '/legal/agreements': { body: AGREEMENTS },
    });
    render(<RightsScreen client={client} />);
    // `revocation_effect` 的类型注释写着：必须在点撤回**之前**展示
    await waitFor(() => expect(
      screen.getByText(`撤回后：${SCOPE.revocation_effect}`),
    ).toBeTruthy());
  });

  it('撤回要两步：第一下只是确认，不会真的撤回', async () => {
    const calls: Call[] = [];
    const client = makeClient({
      '/finance/my-tax': { body: TAX },
      '/legal/agreements': { body: AGREEMENTS },
      '/legal/consents/id_document/revoke': { body: { scope: 'id_document', revoked: true, effect: '', applied: ['实名失效', '提现停止'] } },
    }, calls);
    render(<RightsScreen client={client} />);
    fireEvent.press(await screen.findByText('撤回同意'));
    // 手机上误触一下的代价是账号立刻不能接单、不能提现
    expect(calls.some((c) => c.path.includes('/revoke'))).toBe(false);
    expect(screen.getByText('不撤回')).toBeTruthy();

    fireEvent.press(screen.getByText('确认撤回'));
    await waitFor(() => expect(calls.some((c) => c.path === '/legal/consents/id_document/revoke')).toBe(true));
    // 实际生效项由服务端给（applied），客户端不自己罗列
    expect(screen.getByText('已撤回：实名失效、提现停止')).toBeTruthy();
  });

  it('履约必需的同意项不给撤回按钮点下去', async () => {
    const client = makeClient({
      '/finance/my-tax': { body: TAX },
      '/legal/agreements': {
        body: { ...AGREEMENTS, sensitive_scopes: [{ ...SCOPE, revocable: false }] },
      },
    });
    render(<RightsScreen client={client} />);
    await waitFor(() => expect(screen.getByText(/这一项是履约必需/)).toBeTruthy());
  });
});

describe('LAW-032 数据主体权利', () => {
  it('权利清单按服务端给的原样列出', async () => {
    const client = makeClient({
      '/finance/my-tax': { body: TAX },
      '/legal/agreements': { body: AGREEMENTS },
    });
    render(<RightsScreen client={client} />);
    // 「有能力但用户找不到」等于没有（rights 的类型注释写着这条）
    await waitFor(() => expect(screen.getByText('· 导出我的数据')).toBeTruthy());
    expect(screen.getByText('· 注销账号并删除数据')).toBeTruthy();
  });

  it('导出走系统分享，并说清这次包含多少类数据', async () => {
    const spy = jest.spyOn(Share, 'share').mockResolvedValue({ action: 'sharedAction' } as never);
    try {
      const client = makeClient({
        '/finance/my-tax': { body: TAX },
        '/legal/agreements': { body: AGREEMENTS },
        '/users/me/export': { body: { profile: {}, tasks: [], wallet: {} } },
      });
      render(<RightsScreen client={client} />);
      fireEvent.press(await screen.findByText('导出我的数据'));
      // 手机上没有「下载到磁盘」，所以走系统分享——用户可以存进备忘录或发给自己
      await waitFor(() => expect(spy).toHaveBeenCalled());
      // 分享的是文本，系统可能截断；所以同时告诉他这次包含多少类，
      // 而不是只拿到一段不知完整与否的字符串
      expect(screen.getByText('已发起导出：包含 3 类数据')).toBeTruthy();
    } finally {
      spy.mockRestore();
    }
  });
});
