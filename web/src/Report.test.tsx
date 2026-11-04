// RISK-010~014（399 号 spec，V426）举报入口：任务、动态、个人空间、私信旁边都有；自己的不画；
// 选类型、写说明后提交；重复举报说清还在处理；错误码用人话；客服页能看到「我的举报」和处理结果。
import { PlatformClient } from '@platform/core';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { ReportButton } from './Report';
import { AppProvider } from './store';

const ME = { id: 2, phone: '138****0002', nickname: '我', bio: '', city: '上海', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2' };
type Call = { method: string; path: string; body?: unknown };
const TASK = (extra: Record<string, unknown>) => ({ id: 60, title: '装扶手', description: '', category: '维修', status: 'published', budget_cents: 20000,
  creator_id: 9, executor_id: null, is_remote: false, city: '上海', address_hint: '', address_exact: '', parent_id: null,
  task_type: 'service', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none', ...extra });
const POST = (id: number, followed: boolean | null) => ({ id, author_id: followed === null ? 2 : 7, author_nickname: followed === null ? '我' : '别人',
  kind: 'post', title: '', body: `动态${id}`, like_count: 0, comment_count: 0, liked_by_me: false, created_at: '2026-11-04T01:00:00Z',
  author_followed_by_viewer: followed, media_urls: [] });

type Reply = (method: string, path: string, body: unknown) => { status?: number; body: unknown } | undefined;

function open(route: string, calls: Call[], reply: Reply) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    const body = init?.body ? JSON.parse(init.body) : undefined;
    calls.push({ method, path: p, body });
    const r = reply(method, p, body) ?? { body: p === '/users/me' ? ME : [] };
    const status = r.status ?? 200;
    return { ok: status < 300, status, text: async () => JSON.stringify(r.body) };
  }) as unknown as typeof fetch;
  const client = new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
  render(<MemoryRouter initialEntries={[route]}><AppProvider client={client}><App /></AppProvider></MemoryRouter>);
  return client;
}

afterEach(() => { cleanup(); localStorage.clear(); });

describe('RISK-010 举报入口', () => {
  it('别人发的任务有「举报任务」；选类型写说明提交，请求带上类型，提示去「我的举报」看结果', async () => {
    const calls: Call[] = [];
    open('/tasks/60', calls, (m, p) => p === '/tasks/60' ? { body: TASK({}) }
      : m === 'POST' && p === '/reports' ? { status: 201, body: { id: 5, status: 'pending', duplicate: false } } : undefined);
    fireEvent.click(await screen.findByRole('button', { name: '举报这条任务' }));
    const submit = screen.getByRole('button', { name: '提交举报' });
    expect((submit as HTMLButtonElement).disabled).toBe(true);                         // 说明不到 2 个字不能交
    fireEvent.change(screen.getByLabelText('举报类型'), { target: { value: 'fraud' } });
    fireEvent.change(screen.getByLabelText('举报说明'), { target: { value: '要求先转定金到私人账户' } });
    fireEvent.click(submit);
    await screen.findByText(/我的举报/);
    expect(calls.find((c) => c.method === 'POST' && c.path === '/reports')?.body).toEqual(
      { target_type: 'task', target_id: 60, reason: '要求先转定金到私人账户', category: 'fraud' });
  });

  it('自己发的任务没有举报按钮', async () => {
    open('/tasks/60', [], (_m, p) => p === '/tasks/60' ? { body: TASK({ creator_id: 2 }) } : undefined);
    await screen.findByText('装扶手');
    expect(screen.queryByRole('button', { name: '举报这条任务' })).toBeNull();
  });

  it('动态流：别人的动态能举报，自己的不画', async () => {
    open('/community', [], (_m, p) => p === '/feed' ? { body: [POST(1, false), POST(2, null)] } : undefined);
    await screen.findByText('动态1');
    expect(screen.getAllByRole('button', { name: '举报这条内容' })).toHaveLength(1);
  });

  it('别人的个人空间能举报这个用户', async () => {
    open('/people/7', [], (_m, p) => p === '/spaces/7' || p === '/users/7/space'
      ? { body: { user_id: 7, nickname: '别人', kind: 'person', headline: '', introduction: '', theme: 'clay', items: [], accepting_orders: true } }
      : p === '/users/7/follow-stats' ? { body: { followers: 0, following: 0, viewer_following: false } } : undefined);
    await screen.findByRole('button', { name: '举报这条用户' });
  });
});

describe('RISK-011/012 提交结果', () => {
  function single(reply: Reply) {
    const calls: Call[] = [];
    const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
      const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
      const r = reply(init?.method ?? 'GET', p, init?.body ? JSON.parse(init.body) : undefined) ?? { body: {} };
      calls.push({ method: init?.method ?? 'GET', path: p });
      const status = r.status ?? 200;
      return { ok: status < 300, status, text: async () => JSON.stringify(r.body) };
    }) as unknown as typeof fetch;
    localStorage.setItem('token', 'tok');
    render(<MemoryRouter><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}>
      <ReportButton targetType="message" targetId={31} /></AppProvider></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: '举报这条私信' }));
    fireEvent.change(screen.getByLabelText('举报说明'), { target: { value: '一直骚扰' } });
    fireEvent.click(screen.getByRole('button', { name: '提交举报' }));
    return calls;
  }

  it('重复举报：说清已经在处理，不让人以为又交了一次', async () => {
    single((m, p) => m === 'POST' && p === '/reports' ? { body: { id: 3, status: 'pending', duplicate: true } } : undefined);
    expect((await screen.findByRole('status')).textContent).toContain('已经举报过');
  });

  it('举报自己的：服务端错误码翻成人话，表单留着', async () => {
    single((m, p) => m === 'POST' && p === '/reports'
      ? { status: 400, body: { detail: { code: 'report_own_target', message: 'x' } } } : undefined);
    await screen.findByText(/这是你自己的/);
    expect((screen.getByLabelText('举报说明') as HTMLTextAreaElement).value).toBe('一直骚扰');
  });
});

describe('RISK-013 我的举报', () => {
  it('客服页列出我的举报与处理结果；畸形响应不崩', async () => {
    open('/support', [], (_m, p) => p === '/reports/mine' ? { body: { categories: {}, items: [
      { id: 8, target_type: 'content', target_id: 4, category: 'porn', category_label: '色情低俗', reason: '露骨图片', status: 'resolved',
        result: '已下架违规内容', created_at: '2026-11-04T01:00:00Z', resolved_at: '2026-11-04T03:00:00Z' },
      { id: 9, target_type: 'user', target_id: 5, category: 'other', category_label: '其他', reason: '冒充', status: 'pending',
        result: '', created_at: '2026-11-04T02:00:00Z', resolved_at: null }] } } : undefined);
    const row = await screen.findByTestId('report-8');
    expect(row.textContent).toContain('内容 #4');
    expect(row.textContent).toContain('已处理：已下架违规内容');
    expect(screen.getByTestId('report-9').textContent).toContain('处理中');
  });

  it('响应不是列表时显示「还没有举报过」', async () => {
    open('/support', [], (_m, p) => p === '/reports/mine' ? { body: { items: 'oops' } } : undefined);
    await waitFor(() => expect(screen.getByLabelText('我的举报').textContent).toContain('还没有举报过'));
  });
});

describe('RISK-016 处置队列：最急的在前与处理时限（401 号 spec）', () => {
  it('默认按编号请求；勾上「最急的在前」带 sort=urgent；超时的标出来', async () => {
    const calls: Call[] = [];
    const ADMIN = { ...ME, is_admin: true };
    localStorage.setItem('token', 'tok');
    const fetchImpl = vi.fn(async (url: string, init?: { method?: string }) => {
      const full = String(url).replace(/^.*\/api\/v1/, '');
      const p = full.split('?')[0];
      calls.push({ method: init?.method ?? 'GET', path: full });
      const body = p === '/users/me' ? ADMIN : p === '/admin/metrics' ? { total_users: 0, verified_users: 0, total_tasks: 0, published_tasks: 0,
        completed_tasks: 0, closed_loop_rate: 0, dispute_count: 0, gmv_cents: 0, fee_income_cents: 0 }
        : p === '/admin/reports' ? [
          { id: 3, reporter_id: 2, target_type: 'user', target_id: 9, reason: '冒充客服', created_at: '2026-11-03T00:00:00Z', category: 'fraud',
            urgent: true, waited_hours: 30, sla_hours: 24, overdue: true },
          { id: 1, reporter_id: 2, target_type: 'content', target_id: 4, reason: '不喜欢', created_at: '2026-11-04T00:00:00Z', category: 'other',
            urgent: false, waited_hours: 2, sla_hours: 72, overdue: false }] : [];
      return { ok: true, status: 200, text: async () => JSON.stringify(body) };
    }) as unknown as typeof fetch;
    render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}>
      <App /></AppProvider></MemoryRouter>);
    await screen.findByText('冒充客服');
    expect(calls.some((c) => c.path === '/admin/reports?status=pending')).toBe(true);
    expect(screen.getByTestId('report-sla-3').textContent).toContain('已超时');
    expect(screen.getByTestId('report-sla-1').textContent).toBe('已等 2 小时（72 小时内处理）');
    expect(screen.getByTestId('reports-overdue').textContent).toContain('1 条');
    fireEvent.click(screen.getByLabelText('最急的在前'));
    await waitFor(() => expect(calls.some((c) => c.path === '/admin/reports?status=pending&sort=urgent')).toBe(true));
  });
});
