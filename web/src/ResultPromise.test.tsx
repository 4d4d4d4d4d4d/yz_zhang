// SCN-185（311 号 spec）发单人看报名列表：留言里承诺了结果的标出来（不拦）；没承诺的照旧。
import { PlatformClient } from '@platform/core';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 1, phone: '138****0000', nickname: '发布方', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0 };
const TASK = { id: 7, title: '改简历', description: '', category: '求职辅导', status: 'published', budget_cents: 20000,
  creator_id: 1, executor_id: null, is_remote: true, city: '', address_hint: '', address_exact: '', parent_id: null,
  task_type: 'simple', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none' };
const FLAG = '这条报名承诺了结果（保 offer、包过之类）：录用、录取由对方机构决定，谁也保证不了，选人时多留个心';
const APPS = [
  { id: 21, applicant_id: 5, nickname: '甲', credit_score: 100, rating_avg: 0, bid_cents: 20000, message: '包就业', status: 'pending', promise_flag: FLAG },
  { id: 22, applicant_id: 6, nickname: '乙', credit_score: 100, rating_avg: 0, bid_cents: 20000, message: '改两轮', status: 'pending' },
];

describe('SCN-185 报名留言里的结果承诺', () => {
  it('承诺了的标出来，没承诺的不标', async () => {
    localStorage.setItem('token', 'tok');
    const routes: Record<string, unknown> = { '/users/me': ME, '/tasks/7': TASK, '/tasks/7/applications': APPS };
    const fetchImpl = vi.fn(async (url: string) => {
      const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
      return { ok: true, status: 200, text: async () => JSON.stringify(path in routes ? routes[path] : []) };
    }) as unknown as typeof fetch;
    render(<MemoryRouter initialEntries={['/tasks/7']}>
      <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
    expect((await screen.findByTestId('promise-21')).textContent).toBe(`⚠️ ${FLAG}`);
    expect(screen.queryByTestId('promise-22')).toBeNull();
  });
});
