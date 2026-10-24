// KB-095（267 号 spec）App 发单页「查参考价」：点了才查；与 Web 同一句话，集中时带去重说明。
import { fireEvent, render, screen } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { PublishScreen } from './App';

function makeClient(ref: unknown, paths: string[]) {
  const fetchImpl = (async (url: string) => {
    const full = String(url).replace(/^.*\/api\/v1/, '');
    paths.push(full);
    const path = full.split('?')[0];
    return { ok: true, status: 200, text: async () => JSON.stringify(path === '/knowledge/price-reference' ? ref : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('KB-095 App 查参考价', () => {
  it('点了才按类目查；集中时写明去重后的中位价', async () => {
    const paths: string[] = [];
    render(<PublishScreen client={makeClient({ sample_size: 9, p50_cents: 5000, min_cents: 5000, max_cents: 22000, publishers: 5,
      p50_by_publisher_cents: 18000, top_publisher_share: 0.556, concentrated: true,
      note: '这 9 单里有 5 单来自同一位发布方；按发布方去重后，5 位发布方的中位价是 ¥180.00，更能代表行情' }, paths)}
      onDone={() => undefined} category="保洁" />);
    expect(paths.some((p) => p.startsWith('/knowledge/price-reference'))).toBe(false);
    fireEvent.press(screen.getByText('查参考价'));
    expect(await screen.findByText(/同类闭环任务 9 单：中位价 ¥50.00（¥50.00 ~ ¥220.00）。这 9 单里有 5 单/)).toBeTruthy();
    expect(paths.find((p) => p.startsWith('/knowledge/price-reference'))).toContain(`category=${encodeURIComponent('保洁')}`);
  });

  it('没有样本时说服务端的话', async () => {
    render(<PublishScreen client={makeClient({ sample_size: 0, message: '暂无同类闭环数据，建议参考平台模板报价' }, [])} onDone={() => undefined} />);
    fireEvent.press(screen.getByText('查参考价'));
    expect(await screen.findByText('暂无同类闭环数据，建议参考平台模板报价')).toBeTruthy();
  });
});
