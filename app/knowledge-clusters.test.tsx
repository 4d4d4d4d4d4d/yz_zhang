// KB-073/074 App 上按子类看经验（108 号 spec）。
import { fireEvent, render, screen } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { SubclassesBlock } from './ask';

function makeClient(routes: Record<string, unknown>): PlatformClient {
  const fetchImpl = (async (url: string) => {
    const path = decodeURIComponent(String(url).replace(/^.*\/api\/v1/, '')).split('?')[0];
    return { ok: true, status: 200, text: async () => JSON.stringify(routes[path] ?? []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

function cluster(id: number, over: Record<string, unknown> = {}) {
  return {
    id, category: '跑腿', label: `跑腿·同城代取${id}`, status: 'active', merged_into: null,
    sample_count: 12, price_p50_cents: 20000, price_p90_cents: 35000, duration_p50_days: 0,
    duration_p90_days: 1, priced_samples: 10, outcome_mix: { completed: 10, disputed: 1, cancelled: 1 },
    first_sample_at: '2026-06-01T00:00:00Z', last_sample_at: '2026-10-01T00:00:00Z', recent_share: 0.8,
    few_samples: false, note: '', created_by: 'auto', ...over,
  };
}

describe('KB-073/074 App 按子类看', () => {
  it('带样本量、价格分布与纠纷取消；样本少的不给价', async () => {
    render(<SubclassesBlock client={makeClient({ '/knowledge/clusters': { semantic: true, model: 'm', items: [
      cluster(1), cluster(2, { sample_count: 2, few_samples: true, note: '样本过少（2 个），仅供参考', price_p50_cents: 9900 }),
    ] } })} />);
    fireEvent.press(screen.getByText('按子类看'));
    const big = await screen.findByText(/^12 个样本/);
    expect(big.props.children).toMatch(/价格中位 ¥200\.00/);
    expect(big.props.children).toMatch(/有纠纷 1 \/ 取消 1/);
    const small = await screen.findByText(/^2 个样本/);
    expect(small.props.children).not.toMatch(/价格中位/);
    expect(screen.getByText(/样本过少/)).toBeTruthy();
  });

  it('详情：共识与分歧一起给，只出现一次的只数不展示', async () => {
    render(<SubclassesBlock client={makeClient({
      '/knowledge/clusters': { semantic: true, model: 'm', items: [cluster(1)] },
      '/knowledge/clusters/1': { ...cluster(1), consensus_steps: [{ title: '接单确认', count: 8 }],
        dissent: [{ steps: ['约时间', '上门代办'], count: 2 }], dissent_hidden: 3, steps_basis: 10,
        evidence: { shown: [], hidden: 12, note: '个案需双方授权后才能展示' } },
    })} />);
    fireEvent.press(screen.getByText('按子类看'));
    fireEvent.press(await screen.findByText('跑腿·同城代取1 ›'));
    expect(await screen.findByText(/1\. 接单确认/)).toBeTruthy();
    expect(screen.getByText(/约时间 → 上门代办/)).toBeTruthy();
    expect(screen.getByText(/另有 3 种只出现过一次的做法/)).toBeTruthy();
    expect(screen.getByText(/个案需双方授权/)).toBeTruthy();
  });

  it('没有子类时说清不是出错', async () => {
    render(<SubclassesBlock client={makeClient({ '/knowledge/clusters': { semantic: false, model: 'local', items: [] } })} />);
    fireEvent.press(screen.getByText('按子类看'));
    expect(await screen.findByText(/还没有子类/)).toBeTruthy();
  });
});
