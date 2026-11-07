// SCN-125 验收前的上门回报提醒（179 号 spec）：少回报或有漏项时确认框先说清差多少，取消就不放款；齐了不多问。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 9, phone: '138****0009', nickname: '主人', bio: '', city: '上海', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r9' };
type Call = { method: string; path: string };
const TASK = { id: 70, title: '上门喂猫 7 天', description: '', category: '宠物照护', status: 'pending_acceptance', budget_cents: 50000,
  creator_id: 9, executor_id: 2, is_remote: false, city: '上海', address_hint: '', address_exact: '', parent_id: null,
  task_type: 'service', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none',
  visits_planned: 14, visit_checklist: ['喂食'] };
const visits = (reported: number, missed: number) => ({ task_id: 70, planned: 14, checklist: ['喂食'], reported, missed_total: missed, visits: [] });

function open(calls: Call[], v: unknown) {
  localStorage.setItem('token', 'tok');
  const routes: Record<string, unknown> = { '/users/me': ME, '/tasks/70': TASK, '/tasks/70/visits': v };
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path: p });
    return { ok: true, status: 200, text: async () => JSON.stringify(routes[p] ?? []) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/tasks/70']}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

afterEach(() => vi.restoreAllMocks());

describe('SCN-125 验收前提醒', () => {
  it('少回报：面板上写明差距；确认框说清，取消就不放款', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const calls: Call[] = [];
    open(calls, visits(12, 1));
    expect((await screen.findByLabelText('验收前提醒')).textContent)
      .toBe('计划上门 14 次，回报了 12 次；回报里一共有 1 项没做。验收前可以先问问接单的人。');
    fireEvent.click(screen.getByText('验收通过（放款）'));
    await waitFor(() => expect(confirmSpy).toHaveBeenCalled());
    expect(confirmSpy.mock.calls[0][0]).toContain('回报了 12 次');
    expect(calls.some((c) => c.path === '/tasks/70/accept-delivery')).toBe(false);
  });

  it('确认了才放款', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const calls: Call[] = [];
    open(calls, visits(12, 0));
    await screen.findByLabelText('验收前提醒');
    fireEvent.click(screen.getByText('验收通过（放款）'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/tasks/70/accept-delivery')).toBe(true));
  });

  it('都齐了：不多问', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const calls: Call[] = [];
    open(calls, visits(14, 0));
    await screen.findByText('上门回报 · 14/14 次');
    expect(screen.queryByLabelText('验收前提醒')).toBeNull();
    fireEvent.click(screen.getByText('验收通过（放款）'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/tasks/70/accept-delivery')).toBe(true));
    expect(confirmSpy).not.toHaveBeenCalled();
  });
});

describe('SCN-136 验收确认里写明到场次数', () => {
  it('回报都齐了但只有一次带了到场打卡：面板写明，确认框也说', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const calls: Call[] = [];
    open(calls, { ...visits(14, 0), at_site: 1 });
    expect((await screen.findByLabelText('到场次数')).textContent).toBe('14 次回报里有 1 次带了到场打卡');
    fireEvent.click(screen.getByText('验收通过（放款）'));
    await waitFor(() => expect(confirmSpy).toHaveBeenCalled());
    expect(confirmSpy.mock.calls[0][0]).toContain('14 次回报里有 1 次带了到场打卡');
    expect(calls.some((c) => c.path === '/tasks/70/accept-delivery')).toBe(false);
  });

  it('打不了卡的单（at_site 为 null）不写到场次数', async () => {
    open([], { ...visits(14, 0), at_site: null });
    await screen.findByText('上门回报 · 14/14 次');
    expect(screen.queryByLabelText('到场次数')).toBeNull();
  });
});
