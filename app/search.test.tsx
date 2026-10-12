// SRCH-001/003 全站搜索在 App 上（101 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { SearchScreen } from './search';

const RESULTS = {
  tasks: [{ id: 7, title: '上门保洁两小时', category: '保洁', budget_cents: 20000, city: '上海' }],
  users: [{ id: 5, nickname: '王阿姨', skills: ['保洁', '收纳'], credit_score: 120, rating_avg: 4.9 }],
  contents: [{ id: 3, kind: 'post', title: '保洁验收怎么拍照', body: '前后对比…', author_id: 5 }],
  circles: [{ id: 1, name: '上海家政圈', kind: 'interest', member_count: 42 }],
};

function makeClient(routes: Record<string, unknown>): PlatformClient {
  const fetchImpl = (async (url: string) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const hit = Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('SRCH-001 App 全站搜索', () => {
  it('点热词就搜；点人打开空间、点任务打开详情', async () => {
    const onOpenSpace = jest.fn();
    const onOpenTask = jest.fn();
    render(<SearchScreen
      client={makeClient({ '/search/trending': [{ term: '保洁', count: 9 }], '/search': RESULTS })}
      onOpenSpace={onOpenSpace} onOpenTask={onOpenTask} />);
    fireEvent.press(await screen.findByText('保洁'));
    fireEvent.press(await screen.findByText('王阿姨'));
    expect(onOpenSpace).toHaveBeenCalledWith(5);
    fireEvent.press(screen.getByText('上门保洁两小时'));
    expect(onOpenTask).toHaveBeenCalledWith(7);
    expect(screen.getByText('保洁验收怎么拍照')).toBeTruthy();
    expect(screen.getByText('上海家政圈')).toBeTruthy();
  });

  it('没有结果时说清楚', async () => {
    render(<SearchScreen
      client={makeClient({ '/search': { tasks: [], users: [], contents: [], circles: [] } })}
      onOpenSpace={() => {}} onOpenTask={() => {}} />);
    fireEvent.changeText(screen.getByPlaceholderText('搜任务、人、内容、圈层…'), '火星');
    fireEvent(screen.getByPlaceholderText('搜任务、人、内容、圈层…'), 'submitEditing');
    await waitFor(() => expect(screen.getByText(/没有找到相关结果/)).toBeTruthy());
  });

  it('打字时给联想，点联想就搜', async () => {
    render(<SearchScreen
      client={makeClient({ '/search/suggest': ['保洁阿姨'], '/search': RESULTS })}
      onOpenSpace={() => {}} onOpenTask={() => {}} />);
    fireEvent.changeText(screen.getByPlaceholderText('搜任务、人、内容、圈层…'), '保');
    fireEvent.press(await screen.findByText('保洁阿姨', {}, { timeout: 2000 }));
    await waitFor(() => expect(screen.getByText('上门保洁两小时')).toBeTruthy());
  });
});
