// SCN-181（307 号 spec）一个类目要多张资质：发布页全部列出；后台「城市与类目」显示全部资质、能设其余资质。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 2, phone: '138****0002', nickname: '新手妈妈', bio: '', city: '上海', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2' };
const CATS = [{ id: 1, name: '母婴护理', required_cert: '健康证明', extra_certs: ['无犯罪记录证明'] },
  { id: 2, name: '上门做饭', required_cert: '健康证明' }, { id: 3, name: '跑腿', required_cert: '' }];
type Call = { method: string; path: string; query: string; body?: unknown };

function open(at: string, me: unknown, calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const [p, q = ''] = String(url).replace(/^.*\/api\/v1/, '').split('?');
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, query: decodeURIComponent(q), body: init?.body ? JSON.parse(init.body) : undefined });
    const body = p === '/users/me' ? me : p === '/categories' ? CATS : p === '/cities' ? [{ id: 1, name: '上海' }]
      : p === '/admin/admins' ? { admins: [] } : p === '/admin/aml/activities' ? { items: [], note: '' }
      : method === 'PATCH' ? { id: 2, name: '上门做饭', active: true, required_cert: '健康证明' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={[at]}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('SCN-181 一个类目要多张资质', () => {
  it('发布页：选母婴护理时列出两张资质；只要一张的照旧', async () => {
    open('/publish?title=%E6%89%BE%E8%82%B2%E5%84%BF%E5%AB%82&category=%E6%AF%8D%E5%A9%B4%E6%8A%A4%E7%90%86&city=%E4%B8%8A%E6%B5%B7', ME, []);
    expect(await screen.findByText('⚠️ 该类目为受限类目，仅持「健康证明」「无犯罪记录证明」资质的执行者可接单')).toBeTruthy();
    fireEvent.change(screen.getByDisplayValue('母婴护理'), { target: { value: '上门做饭' } });
    expect(await screen.findByText('⚠️ 该类目为受限类目，仅持「健康证明」资质的执行者可接单')).toBeTruthy();
    fireEvent.change(screen.getByDisplayValue('上门做饭'), { target: { value: '跑腿' } });
    await waitFor(() => expect(screen.queryByText(/该类目为受限类目/)).toBeNull());
  });

  it('后台：类目表列出全部资质；「其余资质」按顿号发出', async () => {
    const calls: Call[] = [];
    open('/admin', { ...ME, is_admin: true, admin_roles: ['ops'] }, calls);
    const row = (await screen.findByText('母婴护理')).closest('tr')!;
    expect(row.textContent).toContain('健康证明、无犯罪记录证明');
    const cook = screen.getByText('上门做饭').closest('tr')!;
    expect(within(screen.getByText('跑腿').closest('tr')!).queryByText('其余资质')).toBeNull();
    const ask = vi.spyOn(window, 'prompt').mockReturnValue(' 无犯罪记录证明 ');
    try {
      fireEvent.click(within(cook).getByText('其余资质'));
      await waitFor(() => expect(calls.find((c) => c.method === 'PATCH' && c.path === '/admin/categories/2')?.query)
        .toBe('extra_certs=无犯罪记录证明'));
    } finally { ask.mockRestore(); }
  });
});
