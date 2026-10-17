// SCN-107 一单多人、多天（167 号 spec）：发布页写「连续几天、从哪天开始」，带到请求里；一天的照旧不带。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 2, phone: '138****0002', nickname: '店主', bio: '', city: '上海', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2' };
type Call = { method: string; path: string; body?: unknown };

function open(calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const body = p === '/users/me' ? ME : p === '/categories' ? [{ name: '跑腿', required_cert: '' }]
      : p === '/cities' ? [{ id: 1, name: '上海' }] : method === 'POST' && p === '/tasks' ? { id: 50, title: '快闪店帮手', status: 'draft', slots: [] } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/publish?title=%E5%BF%AB%E9%97%AA%E5%BA%97%E5%B8%AE%E6%89%8B&category=%E8%B7%91%E8%85%BF&city=%E4%B8%8A%E6%B5%B7']}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('SCN-107 连续几天的活', () => {
  it('写了 3 天就要选开始日期，请求带 days 与 start_date', async () => {
    const calls: Call[] = [];
    open(calls);
    await screen.findByDisplayValue('快闪店帮手');
    expect(screen.queryByLabelText('从哪天开始')).toBeNull();
    fireEvent.change(screen.getByLabelText('连续几天'), { target: { value: '3' } });
    fireEvent.change(screen.getByLabelText('从哪天开始'), { target: { value: '2030-01-05' } });
    fireEvent.change(screen.getByDisplayValue('— 请选择 —'), { target: { value: 'assign' } });
    fireEvent.submit(screen.getByLabelText('连续几天').closest('form')!);
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks')?.body).toMatchObject({ days: 3, start_date: '2030-01-05' }));
  });

  it('一天的照旧不带 days', async () => {
    const calls: Call[] = [];
    open(calls);
    await screen.findByDisplayValue('快闪店帮手');
    fireEvent.change(screen.getByDisplayValue('— 请选择 —'), { target: { value: 'assign' } });
    fireEvent.submit(screen.getByLabelText('连续几天').closest('form')!);
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/tasks')).toBe(true));
    const body = calls.find((c) => c.method === 'POST' && c.path === '/tasks')!.body as Record<string, unknown>;
    expect('days' in body).toBe(false);
  });

  it('SCN-117 每天几点到几点：写了就带进请求', async () => {
    const calls: Call[] = [];
    open(calls);
    await screen.findByDisplayValue('快闪店帮手');
    fireEvent.change(screen.getByLabelText('连续几天'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('从哪天开始'), { target: { value: '2030-01-05' } });
    fireEvent.change(screen.getByLabelText('每天几点开始'), { target: { value: '09:00' } });
    fireEvent.change(screen.getByLabelText('每天几点结束'), { target: { value: '18:30' } });
    fireEvent.change(screen.getByDisplayValue('— 请选择 —'), { target: { value: 'assign' } });
    fireEvent.submit(screen.getByLabelText('连续几天').closest('form')!);
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks')?.body).toMatchObject(
      { days: 2, shift_start: '09:00', shift_end: '18:30' }));
  });
});

describe('SCN-127 每天时段不一样', () => {
  it('勾上后每天一行，标出日期；空着的那天传 null', async () => {
    const calls: Call[] = [];
    open(calls);
    fireEvent.change(await screen.findByLabelText('连续几天'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('从哪天开始'), { target: { value: '2030-01-05' } });
    fireEvent.click(screen.getByLabelText('每天时段不一样'));
    expect(screen.getByLabelText('每天的时段').textContent).toContain('第 2 天（01-06）');
    fireEvent.change(screen.getByLabelText('第 2 天几点开始'), { target: { value: '10:00' } });
    fireEvent.change(screen.getByLabelText('第 2 天几点结束'), { target: { value: '16:00' } });
    fireEvent.change(screen.getByDisplayValue('— 请选择 —'), { target: { value: 'assign' } });
    fireEvent.submit(screen.getByLabelText('连续几天').closest('form')!);
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks')?.body).toMatchObject(
      { days: 2, day_shifts: [null, { start: '10:00', end: '16:00' }] }));
  });

  it('没勾或一天的单：不带 day_shifts', async () => {
    const calls: Call[] = [];
    open(calls);
    await screen.findByLabelText('连续几天');
    expect(screen.queryByLabelText('每天时段不一样')).toBeNull();   // 一天的单没有这一项
    fireEvent.change(screen.getByLabelText('连续几天'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('从哪天开始'), { target: { value: '2030-01-05' } });
    fireEvent.change(screen.getByDisplayValue('— 请选择 —'), { target: { value: 'assign' } });
    fireEvent.submit(screen.getByLabelText('连续几天').closest('form')!);
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/tasks')).toBe(true));
    expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks')!.body).not.toHaveProperty('day_shifts');
  });
});

describe('SCN-127 填了又取消勾选', () => {
  it('取消「每天时段不一样」后，填过的每天时段不再带上', async () => {
    const calls: Call[] = [];
    open(calls);
    fireEvent.change(await screen.findByLabelText('连续几天'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('从哪天开始'), { target: { value: '2030-01-05' } });
    fireEvent.click(screen.getByLabelText('每天时段不一样'));
    fireEvent.change(screen.getByLabelText('第 1 天几点开始'), { target: { value: '08:00' } });
    fireEvent.change(screen.getByLabelText('第 1 天几点结束'), { target: { value: '12:00' } });
    fireEvent.click(screen.getByLabelText('每天时段不一样'));
    fireEvent.change(screen.getByDisplayValue('— 请选择 —'), { target: { value: 'assign' } });
    fireEvent.submit(screen.getByLabelText('连续几天').closest('form')!);
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/tasks')).toBe(true));
    expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks')!.body).not.toHaveProperty('day_shifts');
  });
});
