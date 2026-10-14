// PROF-100 任务画像与能力画像（126 号 spec）：发布页边写边提示、任务详情的画像、个人资料的能力画像。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { CapabilityCard } from './Profiles';
import { AppProvider } from './store';

const ME = {
  id: 2, phone: '138****0002', nickname: '我', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100,
  rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2',
  weekly_slots: [], limited_capacity: false,
};
type Call = { method: string; path: string; body?: unknown };
const PROFILE = {
  category: '设计', mode: 'remote', declared_skills: [], inferred_skills: ['Figma'], size: 'small',
  price: { sample_size: 3, p50_cents: 50000, min_cents: 40000, max_cents: 60000, position: 'below_min' },
  risks: [{ kind: 'large_amount', text: '金额较大：建议分期（里程碑）托管' }], completeness: 0.43,
  checks: [{ key: 'title', ok: true, hint: '' }, { key: 'acceptance', ok: false, hint: '写清验收标准：做到什么程度算完成' }],
};

function open(path: string, routes: Record<string, unknown>, calls: Call[] = []) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const key = Object.keys(routes).find((k) => k === `${method} ${p}`) ?? Object.keys(routes).find((k) => k === p);
    return { ok: true, status: 200, text: async () => JSON.stringify(key ? routes[key] : (p === '/users/me' ? ME : [])) };
  }) as unknown as typeof fetch;
  const client = new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
  render(<MemoryRouter initialEntries={[path]}><AppProvider client={client}><App /></AppProvider></MemoryRouter>);
  return calls;
}

describe('PROF-100 画像', () => {
  it('发布页：边写边提示缺什么、预算位置、认出的技能与风险；停下来才请求', async () => {
    const calls: Call[] = [];
    open('/publish', { 'POST /profiles/task-draft': PROFILE, '/categories': [{ name: '设计', required_cert: '' }] }, calls);
    const box = await screen.findByLabelText('说明完整度', {}, { timeout: 3000 });
    expect(box.textContent).toContain('说明完整度 43%');
    expect(box.textContent).toContain('低于近期同类最低成交价');
    expect(box.textContent).toContain('写清验收标准');
    expect(box.textContent).toContain('Figma');
    expect(box.textContent).toContain('建议分期');
    const before = calls.filter((c) => c.path === '/profiles/task-draft').length;
    const title = screen.getAllByRole('textbox')[0];
    for (const ch of ['咖', '咖啡', '咖啡店']) fireEvent.change(title, { target: { value: ch } });
    await waitFor(() => expect(calls.filter((c) => c.path === '/profiles/task-draft').length).toBe(before + 1), { timeout: 3000 });
    expect(calls.filter((c) => c.path === '/profiles/task-draft').pop()?.body).toMatchObject({ title: '咖啡店', budget_cents: 20000 });
  });

  it('能力画像：把自述与佐证分开，纠纷只给本人看（个人资料页上就是这一块）', async () => {
    localStorage.setItem('token', 'tok');
    const routes: Record<string, unknown> = { '/users/me/capability': { user_id: 2, tasks_completed: 4, categories: [{ category: '设计', completed: 3, rating_avg: 4.3 }],
      skills: [{ skill: 'Figma', evidenced: true }, { skill: '摄影', evidenced: false }], certifications: ['电工'], on_time_rate: 0.75,
      rework_rate: null, reply_hours_median: 2.5, has_weekly_slots: true, limited_capacity: false, note: '样本少于 3 单的比率不给出', disputes: 0 } };
    const fetchImpl = vi.fn(async (url: string) => {
      const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
      return { ok: true, status: 200, text: async () => JSON.stringify(routes[p] ?? (p === '/users/me' ? ME : [])) };
    }) as unknown as typeof fetch;
    render(<AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><CapabilityCard /></AppProvider>);
    const card = await screen.findByLabelText('能力画像');
    expect(card.textContent).toContain('设计：完成 3 单，平均 4.3 星');
    expect(card.textContent).toContain('Figma（有成交佐证）');
    expect(card.textContent).toContain('摄影（自述）');
    expect(card.textContent).toContain('准时交付 75% · 返工 样本不足');
    expect(card.textContent).toContain('纠纷 0 次（只有你看得到）');
  });
});
