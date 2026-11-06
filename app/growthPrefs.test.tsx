// APP-074d（420 号 spec）App 上的通知开关、新人任务与邀请好友。
import { readFileSync } from 'fs';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { GrowthBlock, NotificationPrefsBlock } from './accountExtras';

type Call = { method: string; path: string };
type Route = { status?: number; body: unknown };

function makeClient(routes: Record<string, Route>, calls: Call[] = []): PlatformClient {
  const fetchImpl = (async (url: string, init?: { method?: string }) => {
    const full = decodeURIComponent(String(url).replace(/^.*\/api\/v1/, ''));
    const method = init?.method ?? 'GET';
    calls.push({ method, path: full });
    const hit = routes[`${method} ${full.split('?')[0]}`] ?? routes[full.split('?')[0]];
    const status = hit?.status ?? 200;
    return { ok: status < 400, status, text: async () => JSON.stringify(hit ? hit.body : {}) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

const PREFS = {
  prefs: { task: true, interaction: false, promo: true },
  always_on_categories: ['funds'],
  always_on: [{ category: 'task', title: '验收即将超时', why: '超时会自动放款' }],
};

describe('NTF-065 App 上的通知开关', () => {
  it('列出类目（说人话，新类目原样），关掉打到 PUT 并重新拉；关不掉的列出来并说明为什么', async () => {
    const calls: Call[] = [];
    render(<NotificationPrefsBlock client={makeClient({
      '/notifications/prefs': { body: PREFS }, 'PUT /notifications/prefs': { body: { category: 'task', enabled: false } },
    }, calls)} />);
    expect(await screen.findByText('任务进展')).toBeTruthy();
    expect(screen.getByText('互动（评论、关注、私信）')).toBeTruthy();
    expect(screen.getByText('promo')).toBeTruthy();
    expect(screen.getByText('· 验收即将超时：超时会自动放款')).toBeTruthy();
    expect(screen.getByText(/资金类（funds）一律送达/)).toBeTruthy();
    fireEvent(screen.getByTestId('pref-task'), 'valueChange', false);
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT' && c.path === '/notifications/prefs?category=task&enabled=false')).toBe(true));
    await waitFor(() => expect(calls.filter((c) => c.path === '/notifications/prefs').length).toBe(2));
  });

  it('关不掉时原样说出服务端的理由', async () => {
    render(<NotificationPrefsBlock client={makeClient({
      '/notifications/prefs': { body: PREFS },
      'PUT /notifications/prefs': { status: 400, body: { detail: { code: 'pref_locked_x', message: '资金类通知不能关闭' } } },
    })} />);
    fireEvent(await screen.findByTestId('pref-task'), 'valueChange', false);
    expect(await screen.findByText('资金类通知不能关闭')).toBeTruthy();
  });

  it('响应畸形：不画', async () => {
    const calls: Call[] = [];
    render(<NotificationPrefsBlock client={makeClient({ '/notifications/prefs': { body: { prefs: null } } }, calls)} />);
    await waitFor(() => expect(calls.length).toBe(1));
    expect(screen.queryByText('通知偏好')).toBeNull();
  });
});

describe('GRW App 上的新人任务与邀请好友', () => {
  it('新人任务打钩、邀请码与战绩', async () => {
    render(<GrowthBlock client={makeClient({
      '/me/newcomer': { body: { steps: [{ key: 'verify', label: '完成实名', done: true }, { key: 'first', label: '完成第一单', done: false }], finished: 1, total: 2, completed: false } },
      '/me/referrals': { body: { referral_code: 'AB12', invited_count: 3, achieved_count: 1, blocked_count: 0, earned_cents: 1000, levels: 1 } },
    })} />);
    expect(await screen.findByText('新人任务 1/2')).toBeTruthy();
    expect(screen.getByText('✅ 完成实名')).toBeTruthy();
    expect(screen.getByText('⬜️ 完成第一单')).toBeTruthy();
    expect(await screen.findByText('我的邀请码：AB12')).toBeTruthy();
    expect(screen.getByText('已邀请 3 人 · 达成 1 人 · 累计奖励 ¥10.00')).toBeTruthy();
  });

  it('新人任务做完了就不再占地方；两样都拿不到就整块不画', async () => {
    const calls: Call[] = [];
    render(<GrowthBlock client={makeClient({
      '/me/newcomer': { body: { steps: [], finished: 2, total: 2, completed: true } }, '/me/referrals': { status: 500, body: {} },
    }, calls)} />);
    await waitFor(() => expect(calls.length).toBe(2));
    expect(screen.queryByText(/新人任务/)).toBeNull();
    expect(screen.queryByText('邀请好友')).toBeNull();
    expect(screen.queryByTestId('growth')).toBeNull();   // 不留一张空卡片
  });

  it('通知页里有开关，「我的」里有新人任务与邀请', () => {
    const src = readFileSync(`${__dirname}/App.tsx`, 'utf8');
    expect(src).toContain('<NotificationPrefsBlock client={client} />');
    expect(src).toContain('<GrowthBlock client={client} />');
  });
});
