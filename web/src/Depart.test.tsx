// SCN-122c（364 号 spec）接单人「出发了」：只有接单人、线下单、待上门时出现；带上选的分钟数；告诉他已经通知了发单人。
import { PlatformClient } from '@platform/core';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { canDepart } from './Depart';
import { AppProvider } from './store';

const ME = { id: 2, phone: '138****0002', nickname: '师傅', bio: '', city: '上海', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2' };
type Call = { method: string; path: string; body?: unknown };
const TASK = (extra: Record<string, unknown>) => ({ id: 60, title: '装扶手', description: '', category: '维修', status: 'in_progress', budget_cents: 20000,
  creator_id: 9, executor_id: 2, is_remote: false, city: '上海', address_hint: '', address_exact: '', parent_id: null,
  task_type: 'service', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none', ...extra });

function open(calls: Call[], task: Record<string, unknown>) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const body = p === '/tasks/60' ? task : p === '/users/me' ? ME
      : method === 'POST' && p === '/tasks/60/depart' ? { id: 1, departed_at: '2026-11-03T01:00:00Z', eta_at: '2026-11-03T01:45:00Z', updated: false } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/tasks/60']}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('SCN-122c 出发了', () => {
  it('只有接单人、线下单、待上门时能报', () => {
    expect(canDepart({ is_remote: false, status: 'in_progress', executor_id: 2 }, 2)).toBe(true);
    expect(canDepart({ is_remote: false, status: 'matched', executor_id: 2 }, 2)).toBe(true);
    expect(canDepart({ is_remote: true, status: 'in_progress', executor_id: 2 }, 2)).toBe(false);
    expect(canDepart({ is_remote: false, status: 'in_progress', executor_id: 3 }, 2)).toBe(false);
    expect(canDepart({ is_remote: false, status: 'completed', executor_id: 2 }, 2)).toBe(false);
  });

  it('选分钟数后点「出发了」：请求带上分钟数，提示已告诉发单人', async () => {
    const calls: Call[] = [];
    open(calls, TASK({}));
    await screen.findByLabelText('出发了');
    fireEvent.change(screen.getByLabelText('预计多少分钟到'), { target: { value: '45' } });
    fireEvent.click(screen.getByText('出发了', { selector: 'button' }));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks/60/depart')?.body).toEqual({ eta_minutes: 45 }));
    expect((await screen.findByRole('status')).textContent).toContain('已告诉发单人');
  });

  it('发单人、线上单看不到', async () => {
    for (const extra of [{ executor_id: 5 }, { is_remote: true }]) {
      open([], TASK(extra));
      await screen.findByText('装扶手');
      expect(screen.queryByLabelText('出发了')).toBeNull();
      cleanup();
    }
  });
});
