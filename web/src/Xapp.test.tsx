// XAPP 跨 App 助手在 Web 上（161 号 spec）。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 1, phone: '138****0000', nickname: '我', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0 };
const STEP = (id: number, extra: Record<string, unknown> = {}) => ({ id, seq: id, app: 'com.tencent.mm', action: 'open', action_label: '打开',
  intent: `第 ${id} 步`, channel: 'deeplink', vision_where: 'device', red_line: false, needs_confirm: false, confirmed: false,
  status: 'done', attempts: 1, result: '', ...extra });
const RUN = { id: 9, grant_id: 1, goal: '告诉客户预计到达时间', executor: 'android', confirm_mode: 'red_only', status: 'running',
  stop_reason: '', created_at: '2026-10-15T00:00:00Z', finished_at: null };

describe('XAPP Web 上的跨 App 助手', () => {
  it('列出授权与执行记录；看步骤时红线步标出「要你亲手完成」；可以撤销、确认、叫停', async () => {
    localStorage.setItem('token', 'tok');
    const calls: Array<{ method: string; path: string }> = [];
    const fetchImpl = vi.fn(async (url: string, init?: { method?: string }) => {
      const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
      const method = init?.method ?? 'GET';
      calls.push({ method, path });
      const body: unknown = path === '/users/me' ? ME
        : path === '/xapp/catalog' ? { actions: [], red_line: [], channels: [], executors: [], notice: '付款、签署只能由你亲手完成。' }
        : path === '/xapp/grants' && method === 'GET' ? [{ id: 1, device_label: '我的手机', apps: ['com.tencent.mm'], actions: ['open'],
            allow_cloud_vision: false, expires_at: '2026-10-22T00:00:00Z', revoked_at: null, active: true, created_at: '2026-10-15T00:00:00Z' }]
        : path === '/xapp/runs' ? [RUN]
        : path === '/xapp/runs/9' ? { ...RUN, steps: [STEP(1, { result: '已打开' }), STEP(2, { action: 'send_message', action_label: '对外发消息', red_line: true, needs_confirm: true, status: 'pending' })] }
        : method === 'POST' || method === 'DELETE' ? { ...RUN, run_status: 'running', step: STEP(2), runs_stopped: 1 } : [];
      return { ok: true, status: 200, text: async () => JSON.stringify(body) };
    }) as unknown as typeof fetch;
    render(<MemoryRouter initialEntries={['/xapp']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
    expect((await screen.findByTestId('xapp-notice')).textContent).toContain('执行在你自己的设备上进行');
    expect((await screen.findByLabelText('授权')).textContent).toContain('屏幕只在本机处理');
    fireEvent.click(await screen.findByText('看步骤'));
    expect((await screen.findByTestId('xapp-step-2')).textContent).toContain('要你亲手完成');
    fireEvent.click(screen.getByText('我已亲手完成'));
    await waitFor(() => expect(calls.some((c) => c.path === '/xapp/runs/9/steps/2/confirm')).toBe(true));
    fireEvent.click(screen.getByText('一键叫停'));
    await waitFor(() => expect(calls.some((c) => c.path === '/xapp/runs/9/stop')).toBe(true));
    fireEvent.click(screen.getByText('撤销'));
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.path === '/xapp/grants/1')).toBe(true));
  });
});
