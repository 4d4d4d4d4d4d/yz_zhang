// NTF-072（261 号 spec）公告「看曲线」：发出后 1 小时 / 1 天 / 3 天 / 7 天内点开的累计人数；没到的时间点写明。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ADMIN = { id: 1, phone: '138****0001', nickname: '运营', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['ops'], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r1' };
const SENT = { id: 5, title: '佣金下调', body: '', verified_only: false, status: 'sent', scheduled_at: null, created_by: 1,
  created_at: '2026-10-14T00:00:00Z', sent_at: '2026-10-14T00:00:00Z', delivered: 200, closed_by: null, closed_at: null, close_reason: '',
  read: 90, read_rate: 0.45 };
const SCHED = { ...SENT, id: 6, title: '维护通知', status: 'scheduled', scheduled_at: '2026-10-16T12:00:00Z', sent_at: null, delivered: 0, read: 0, read_rate: null };
const CURVE = { announcement_id: 5, sent_at: '2026-10-14T00:00:00Z', delivered: 200, read: 90, untimed: 10,
  points: [{ hours: 1, label: '1 小时', read: 40, read_rate: 0.2, reached: true }, { hours: 24, label: '1 天', read: 70, read_rate: 0.35, reached: true },
    { hours: 72, label: '3 天', read: 80, read_rate: 0.4, reached: false }, { hours: 168, label: '7 天', read: 80, read_rate: 0.4, reached: false }],
  note: '另有 10 人点开的时间不详（早于记录点开时间的版本），只算进总数' };

function open(paths: string[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    paths.push(`${init?.method ?? 'GET'} ${path}`);
    const body: unknown = path === '/users/me' ? ADMIN
      : path === '/admin/announcements' ? [SCHED, SENT]
      : path === '/admin/announcements/5/read-curve' ? CURVE
      : path === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('NTF-072 阅读曲线', () => {
  it('已发出的公告点「看曲线」才加载；逐个时间点写累计人数与比例，没到的写明，时间不详的单独说', async () => {
    const paths: string[] = [];
    open(paths);
    const btns = await screen.findAllByText('看曲线');
    expect(btns).toHaveLength(1);                     // 定时未发的没有
    expect(paths).not.toContain('GET /admin/announcements/5/read-curve');
    fireEvent.click(btns[0]);
    const c = await screen.findByTestId('read-curve-5');
    expect(c.textContent).toContain('1 小时内：40 人（20%）');
    expect(c.textContent).toContain('1 天内：70 人（35%）');
    expect(c.textContent).toContain('3 天内：80 人（40%）（还没到，数字是到现在为止的）');
    expect(c.textContent).not.toContain('1 天内：70 人（35%）（还没到');
    expect(c.textContent).toContain('时间不详');
  });
});
