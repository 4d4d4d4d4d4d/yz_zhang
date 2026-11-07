// APP-090 详情页每一块都扛得住畸形响应（182 号 spec）。与 app/detailResilience.test.tsx 同一组组合：
// 每个状态 × 发单人 / 接单人 × 四种畸形响应（{}、null、[]、字符串）× 合约正常 / 合约也畸形，标题必须还在。
// 首次跑时 96 个组合里 70 个白屏：进展、报名、推荐、变更单、纠纷陈述、AI 助理列表拿到非数组就 .map / .some 崩掉。
import { PlatformClient } from '@platform/core';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = (id: number) => ({ id, phone: '138', nickname: 'x', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r' });
const TASK = (status: string) => ({ id: 7, creator_id: 1, executor_id: 2, parent_id: null, depends_on: [], title: '探针', description: '',
  category: '跑腿', task_type: 'service', required_skills: [], budget_cents: 20000, pricing: 'fixed', ip_assignment: 'assign',
  bonus_cents: 0, is_remote: false, city: '上海', lat: 31.2, lng: 121.4, address_hint: '', address_exact: '', deadline: null,
  reject_count: 0, created_at: '2026-10-16T00:00:00Z', visits_planned: 2, visit_checklist: ['a'], days: 2, people_needed: 2, status });
const CONTRACT = { id: 3, task_id: 7, requester_id: 1, executor_id: 2, amount_cents: 20000, released_cents: 0, fee_bps: 800, terms: '',
  status: 'funded', signed_by_requester: true, signed_by_executor: true, frozen: false, version: 1, deposit_cents: 0,
  deposit_status: 'none', milestones: [{ idx: 1, title: '全部', amount_cents: 20000, status: 'pending' }] };
describe('APP-090 Web 任务详情页：任何一块的响应畸形都不许把整页带崩', () => {
  for (const good of [true, false]) for (const [label, body] of [['{}', {}], ['null', null], ['[]', []], ['x', 'x']] as Array<[string, unknown]>)
    for (const status of ['published', 'matched', 'in_progress', 'pending_acceptance', 'completed', 'disputed']) for (const me of [1, 2])
      it(`响应 ${label} · ${status} · ${me === 1 ? '发单人' : '接单人'} · 合约${good ? '正常' : '也畸形'}`, async () => {
        localStorage.setItem('token', 'tok');
        const fetchImpl = vi.fn(async (url: string) => {
          const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
          const out = p === '/users/me' ? ME(me) : p === '/tasks/7' ? TASK(status) : good && p === '/contracts/by-task/7' ? CONTRACT : body;
          return { ok: true, status: 200, text: async () => JSON.stringify(out) };
        }) as unknown as typeof fetch;
        render(<MemoryRouter initialEntries={['/tasks/7']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
        expect(await screen.findByText('探针')).toBeTruthy();
        await new Promise((r) => setTimeout(r, 30));
        expect(screen.getByText('探针')).toBeTruthy();
      });

  const DISPUTE = { id: 11, task_id: 7, status: 'open', reason: '没按时到', initiator_id: 1, respondent_id: 2,
    response_deadline: '2030-01-01T00:00:00Z', created_at: '2026-10-16T00:00:00Z' };
  function openWith(routes: Record<string, unknown>) {
    localStorage.setItem('token', 'tok');
    const fetchImpl = vi.fn(async (url: string) => {
      const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
      const out = p === '/users/me' ? ME(1) : p === '/tasks/7' ? TASK('disputed') : p in routes ? routes[p] : [];
      return { ok: true, status: 200, text: async () => JSON.stringify(out) };
    }) as unknown as typeof fetch;
    render(<MemoryRouter initialEntries={['/tasks/7']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
  }

  it('纠纷响应不像一条纠纷：不画纠纷块（不画出「纠纷 #undefined」）', async () => {
    openWith({ '/tasks/7/dispute': {}, '/disputes/undefined/statements': [] });
    await screen.findByText('探针');
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByText(/纠纷 #/)).toBeNull();
  });

  it('纠纷正常、陈述列表畸形：纠纷块照画，页面不崩', async () => {
    openWith({ '/tasks/7/dispute': DISPUTE, '/disputes/11/statements': { oops: true } });
    expect(await screen.findByText(/纠纷 #11/)).toBeTruthy();
    expect(screen.getByText('探针')).toBeTruthy();
  });
});
