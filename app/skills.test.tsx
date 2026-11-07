// SKL-106 App 上编辑我的技能（135 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { SkillsScreen } from './profiles';

type Call = { method: string; path: string; body?: unknown };
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

describe('SKL-106 App 上的技能', () => {
  it('读出我的技能、写清按什么匹配、保存', async () => {
    const calls: Call[] = [];
    const client = makeClient({
      '/users/me': { id: 2, skills: ['VI设计'] },
      '/skills/concepts': { items: [{ name: '品牌设计', aliases: [] }, { name: '保洁', aliases: [] }] },
      '/skills/normalize': { items: [{ skill: 'VI设计', canonical: '品牌设计', known: true }, { skill: '剪纸', canonical: '剪纸', known: false }] },
      'PATCH /users/me': { id: 2, skills: ['VI设计', '剪纸'] },
    }, calls);
    render(<SkillsScreen client={client} />);
    await waitFor(() => expect(screen.getByLabelText('我的技能').props.value).toBe('VI设计'));
    fireEvent.press(await screen.findByText('保洁'));                     // 平台认得的技能：点一下加进去
    expect(screen.getByLabelText('我的技能').props.value).toBe('VI设计、保洁');
    fireEvent.changeText(screen.getByLabelText('我的技能'), 'VI设计、剪纸');
    expect(await screen.findByText('「VI设计」按「品牌设计」匹配', {}, { timeout: 3000 })).toBeTruthy();
    expect(screen.getByText('「剪纸」平台还不认识，只按原样匹配')).toBeTruthy();
    fireEvent.press(screen.getByText('保存'));
    expect(await screen.findByText('技能已更新')).toBeTruthy();
    expect(calls.find((c) => c.path === '/users/me' && c.method !== 'GET')?.body).toEqual({ skills: ['VI设计', '剪纸'] });
  });
});
