// APP-094 后台「页面出错」（184 号 spec）：运营看到哪一页常坏；别的角色看不到这一块。
import { PlatformClient } from '@platform/core';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = (roles: string[]) => ({ id: 1, phone: '138', nickname: '管理员', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: roles, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [],
  credit_level: '普通', referral_code: 'r' });
const ROWS = [{ platform: 'web', page: '/wallet', kind: 'TypeError', count: 5, people: 3, last_at: '2026-10-16T02:00:00Z' },
  { platform: 'app', page: 'tab-cooperate', kind: 'RangeError', count: 1, people: 1, last_at: '2026-10-15T02:00:00Z' }];

function open(roles: string[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const out = p === '/users/me' ? ME(roles) : p === '/admin/client-errors' ? ROWS : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(out) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('APP-094 后台页面出错', () => {
  it('运营看到哪一页常坏：端、页面、错误类型、次数、人数', async () => {
    open(['ops']);
    const box = await screen.findByLabelText('页面出错');
    await waitFor(() => expect(box.textContent).toContain('网页/walletTypeError53'));
    expect(box.textContent).toContain('Apptab-cooperateRangeError11');
  });

  it('财务看不到这一块', async () => {
    open(['finance']);
    await new Promise((r) => setTimeout(r, 50));
    expect(document.body.textContent).toContain('管理员');
    expect(screen.queryByLabelText('页面出错')).toBeNull();
  });
});

describe('APP-101 后台页面出错：标出已提醒运营的页与阈值', () => {
  it('提醒过的页写「已提醒」和时间，没提醒的写「—」；说明到几个人会提醒', async () => {
    ROWS.splice(0, ROWS.length,
      { platform: 'web', page: '/wallet', kind: 'TypeError', count: 9, people: 6, last_at: '2026-10-16T02:00:00Z', alerted_at: '2026-10-16T03:00:00Z', alert_people: 5 } as never,
      { platform: 'app', page: 'tab-cooperate', kind: 'RangeError', count: 1, people: 1, last_at: '2026-10-15T02:00:00Z', alerted_at: null, alert_people: 5 } as never);
    open(['ops']);
    const box = await screen.findByLabelText('页面出错');
    await waitFor(() => expect(box.textContent).toContain('已提醒'));
    expect(box.textContent).toContain('不同用户到 5 人，会给运营发站内信');
    const rows = box.querySelectorAll('tbody tr');
    expect(rows[0].textContent).toMatch(/已提醒 \d/);
    expect(rows[1].textContent?.endsWith('—')).toBe(true);
  });
});
