// SC-015（296 号 spec）执行方一次交付进行中的几期：列清楚、可写一份交付说明；发布方在分期表里看到说明。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = {
  id: 2, phone: '138****0002', nickname: '执行者', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100,
  rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2',
};
const TASK = {
  id: 7, title: '装修设计', description: '', category: '设计', status: 'in_progress',
  budget_cents: 20000, creator_id: 1, executor_id: 2, is_remote: true, city: '上海',
  address_hint: '', address_exact: '', parent_id: null, task_type: 'service',
  pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none',
};
const ms = (statuses: string[], note = '') => statuses.map((st, i) => ({
  idx: i + 1, title: ['一期', '二期', '三期'][i], amount_cents: [6000, 6000, 8000][i], status: st,
  ...(note && st === 'delivered' ? { delivery_note: note } : {}),
}));
const CONTRACT = (statuses: string[], note = '') => ({
  id: 3, task_id: 7, requester_id: 1, executor_id: 2, amount_cents: 20000, released_cents: 0, fee_bps: 800,
  deposit_cents: 0, deposit_status: 'none', terms: '合同条款', status: 'funded', signed_by_requester: true,
  signed_by_executor: true, frozen: false, version: 1, milestones: ms(statuses, note),
});

function open(me: unknown, contract: unknown, calls: Array<{ method: string; path: string; body: unknown }>) {
  localStorage.setItem('token', 'tok');
  const routes: Record<string, unknown> = {
    '/users/me': me, '/tasks/7': TASK, '/contracts/by-task/7': contract, '/contracts/3/change-orders': [],
    '/contracts/3/milestones/deliver-batch': CONTRACT(['released', 'delivered', 'delivered'], '图纸在附件'),
  };
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path, body: init?.body ? JSON.parse(init.body) : null });
    return { ok: true, status: 200, text: async () => JSON.stringify(routes[path] ?? []) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/tasks/7']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('SC-015 一次交付多期', () => {
  it('执行方：列出要交的几期、写说明后一次交；取消就不发', async () => {
    const calls: Array<{ method: string; path: string; body: unknown }> = [];
    open(ME, CONTRACT(['released', 'pending', 'pending']), calls);
    const ask = vi.spyOn(window, 'prompt').mockReturnValueOnce(null).mockReturnValueOnce(' 图纸在附件 ');
    try {
      fireEvent.click(await screen.findByText('一次交付进行中的 2 期'));
      expect(String(ask.mock.calls[0][0])).toContain('第 2 期 二期 ¥60.00');
      expect(String(ask.mock.calls[0][0])).toContain('第 3 期 三期 ¥80.00');
      expect(calls.some((c) => c.path === '/contracts/3/milestones/deliver-batch')).toBe(false);
      await new Promise((r) => setTimeout(r, 50));
      expect(document.querySelector('.error')).toBeNull();
      fireEvent.click(screen.getByText('一次交付进行中的 2 期'));
      await waitFor(() => expect(calls.find((c) => c.path === '/contracts/3/milestones/deliver-batch')?.body)
        .toEqual({ idxs: [2, 3], note: '图纸在附件' }));
    } finally {
      ask.mockRestore();
    }
  });

  it('只剩一期进行中时不出这个按钮', async () => {
    open(ME, CONTRACT(['released', 'delivered', 'pending']), []);
    await screen.findByText('交付本期');
    expect(screen.queryByText(/一次交付进行中的/)).toBeNull();
  });

  it('发布方：分期表里看到交付说明，不出一次交付的按钮', async () => {
    open({ ...ME, id: 1, nickname: '发布者' }, CONTRACT(['released', 'delivered', 'delivered'], '图纸在附件'), []);
    expect((await screen.findByTestId('ms-note-2')).textContent).toBe('交付说明：图纸在附件');
    expect(screen.getByTestId('ms-note-3')).toBeTruthy();
    expect(screen.queryByTestId('ms-note-1')).toBeNull();
    expect(screen.queryByText(/一次交付进行中的/)).toBeNull();
  });
});
