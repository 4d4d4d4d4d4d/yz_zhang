// TEAM-070（226 号 spec）App 钱包页「团队拨款」。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { TeamReturnsBlock } from './teamReturns';

const ROW = { id: 5, team_id: 9, team_name: '某某科技', purpose: '活动物料', amount_cents: 8000, returned_cents: 3000, returnable_cents: 5000, created_at: '' };

describe('TEAM-070 App 团队拨款', () => {
  it('列出能退的；默认填最多能退的金额；带幂等键退，退清了说结清', async () => {
    const calls: Array<{ path: string; body: unknown; key?: string }> = [];
    let listed = 0;
    const fetchImpl = (async (url: string, init?: { body?: string; headers?: Record<string, string> }) => {
      const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
      calls.push({ path, body: init?.body ? JSON.parse(init.body) : null, key: init?.headers?.['Idempotency-Key'] });
      if (path === '/teams/returnable-spends') { listed += 1; return { ok: true, status: 200, text: async () => JSON.stringify(listed === 1 ? [ROW] : []) }; }
      return { ok: true, status: 200, text: async () => JSON.stringify({ id: 5, returned_cents: 8000, returnable_cents: 0, available_cents: 0 }) };
    }) as unknown as typeof fetch;
    const onChanged = jest.fn();
    render(<TeamReturnsBlock client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })} onChanged={onChanged} />);
    expect(await screen.findByText('某某科技 · 支出 #5（活动物料）：拨给你 ¥80.00，已退 ¥30.00，最多还能退 ¥50.00')).toBeTruthy();
    fireEvent.press(screen.getByText('退回团队'));
    expect(await screen.findByText('已退回 ¥50.00，这笔拨款已全部退清')).toBeTruthy();
    const hit = calls.find((c) => c.path === '/teams/9/spends/5/return')!;
    expect(hit.body).toEqual({ amount_cents: 5000 });
    expect(hit.key).toMatch(/^[0-9a-f]{32}$/);
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });
});
