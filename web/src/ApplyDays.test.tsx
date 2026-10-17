// SCN-118 一个人一次报多天（177 号 spec）：多天母任务上，不是发单人的人勾几天一次报完；名额页能回到整单。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 2, phone: '138****0002', nickname: '帮手', bio: '', city: '上海', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2' };
type Call = { method: string; path: string; body?: unknown };
const BASE = { description: '', category: '跑腿', budget_cents: 10000, is_remote: false, city: '上海', address_hint: '', address_exact: '',
  task_type: 'service', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none', executor_id: null };
const PARENT = { ...BASE, id: 30, title: '快闪店帮手', status: 'published', creator_id: 9, parent_id: null, days: 3, people_needed: 2, work_date: '2030-01-05',
  shift_start: '09:00', shift_end: '18:30' };
const SLOT = { ...BASE, id: 31, title: '快闪店帮手 · 第1天', status: 'published', creator_id: 9, parent_id: 30, days: 1, work_date: '2030-01-05' };
const TREE = { parent_id: 30, parent_status: 'published', progress_pct: 0, all_children_completed: false,
  children: [{ id: 31, title: '名额 31', status: 'published', budget_cents: 1666, depends_on: [], executor_id: null, work_date: '2030-01-05' }],
  by_day: [{ date: '2030-01-05', slots: 2, filled: 2, open: 0, done: 0, closed: 0 },
    { date: '2030-01-06', slots: 2, filled: 0, open: 2, done: 0, closed: 0 },
    { date: '2030-01-07', slots: 2, filled: 1, open: 1, done: 0, closed: 0 }] };

function open(path: string, calls: Call[], routes: Record<string, unknown>, me = ME) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const key = `${method} ${p}`;
    const body = key in routes ? routes[key] : p === '/users/me' ? me : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={[path]}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('SCN-118 一次报多天', () => {
  it('只列还缺人的那几天；勾两天一次报完，并说清哪天没报上', async () => {
    const calls: Call[] = [];
    open('/tasks/30', calls, { 'GET /tasks/30': PARENT, 'GET /tasks/30/tree': TREE,
      'POST /tasks/30/apply-days': { applied: [{ date: '2030-01-06', task_id: 33, application_id: 1 }],
        skipped: [{ date: '2030-01-07', reason: '这一天你已经报过了' }] } });
    const box = await screen.findByLabelText('一次报多天');
    expect(screen.queryByLabelText('报 2030-01-05')).toBeNull();
    fireEvent.click(screen.getByLabelText('报 2030-01-06'));
    fireEvent.click(screen.getByLabelText('报 2030-01-07'));
    fireEvent.click(screen.getByText('报这几天'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks/30/apply-days')?.body).toEqual(
      { dates: ['2030-01-06', '2030-01-07'], message: '' }));
    await waitFor(() => expect(box.textContent).toContain('已报：01-06；没报：01-07（这一天你已经报过了）'));
    // SCN-117 每天的时段写在详情上
    expect(screen.getByLabelText('时段').textContent).toContain('每天 09:00–18:30');
  });

  it('发单人自己看不到「一次报多天」', async () => {
    open('/tasks/30', [], { 'GET /tasks/30': { ...PARENT, creator_id: 2 }, 'GET /tasks/30/tree': TREE });
    await screen.findByLabelText('按天看名额');
    expect(screen.queryByLabelText('一次报多天')).toBeNull();
  });

  it('名额页能回到整单', async () => {
    open('/tasks/31', [], { 'GET /tasks/31': SLOT });
    expect(await screen.findByText('这单一共好几天：回到整单，一次报多天 →')).toBeTruthy();
  });

  it('SCN-126 发单人按人选：一次选同一个人的多天', async () => {
    const calls: Call[] = [];
    open('/tasks/30', calls, { 'GET /tasks/30': { ...PARENT, creator_id: 2 }, 'GET /tasks/30/tree': TREE,
      'GET /tasks/30/applicants': [{ applicant_id: 5, nickname: '小王', days: [
        { date: '2030-01-06', task_id: 33, application_id: 1 }, { date: '2030-01-07', task_id: 35, application_id: 2 }] }],
      'POST /tasks/30/accept-person': { accepted: [{ date: '2030-01-06', task_id: 33, contract_id: 8 }],
        skipped: [{ date: '2030-01-07', reason: '在途任务已达上限' }] } });
    const box = await screen.findByLabelText('按人选');
    expect(box.textContent).toContain('小王 · 01-06、01-07');
    fireEvent.click(screen.getByText('选 TA 的这 2 天'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks/30/accept-person')?.body).toEqual({ applicant_id: 5 }));
    await waitFor(() => expect(box.textContent).toContain('已选 小王：01-06（每天一份合约，去各名额签署、托管）；没选上：01-07（在途任务已达上限）'));
  });

  it('不是发单人看不到「按人选」', async () => {
    open('/tasks/30', [], { 'GET /tasks/30': PARENT, 'GET /tasks/30/tree': TREE,
      'GET /tasks/30/applicants': [{ applicant_id: 5, nickname: '小王', days: [{ date: '2030-01-06', task_id: 33, application_id: 1 }] }] });
    await screen.findByLabelText('一次报多天');
    expect(screen.queryByLabelText('按人选')).toBeNull();
  });
});

describe('SCN-121 发单人补招缺人的那天', () => {
  const POSTER = { ...ME, id: 9, nickname: '店主' };
  it('只列还缺人的日子；选一天、填加价，补招后写明结果', async () => {
    const calls: Call[] = [];
    open('/tasks/30', calls, { 'GET /tasks/30': PARENT, 'GET /tasks/30/tree': TREE,
      'POST /tasks/30/days/2030-01-07/reboost': { date: '2030-01-07', slot_ids: [35], raise_cents: 1050, budget_cents: [2716] } }, POSTER);
    const box = await screen.findByLabelText('补招');
    const select = screen.getByLabelText('补招哪天') as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(['2030-01-06', '2030-01-07']);
    fireEvent.change(select, { target: { value: '2030-01-07' } });
    fireEvent.change(screen.getByLabelText('每个名额加价（元）'), { target: { value: '10.5' } });
    fireEvent.click(screen.getByText('补招这天'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path.endsWith('/reboost'))?.body).toEqual({ raise_cents: 1050 }));
    expect(await screen.findByText('已补招 01-07：1 个还在招的名额再推了一次，每个名额加价 ¥10.50。6 小时后可以再补一次。')).toBeTruthy();
    expect(box).toBeTruthy();
  });

  it('加价写错了不发请求；不是发单人看不到补招', async () => {
    const calls: Call[] = [];
    open('/tasks/30', calls, { 'GET /tasks/30': PARENT, 'GET /tasks/30/tree': TREE }, POSTER);
    await screen.findByLabelText('补招');
    fireEvent.change(screen.getByLabelText('每个名额加价（元）'), { target: { value: '-3' } });
    fireEvent.click(screen.getByText('补招这天'));
    expect(await screen.findByText('加价写一个正数（元），最多两位小数；不加价就空着')).toBeTruthy();
    expect(calls.some((c) => c.path.endsWith('/reboost'))).toBe(false);
  });

  it('帮手看不到补招', async () => {
    open('/tasks/30', [], { 'GET /tasks/30': PARENT, 'GET /tasks/30/tree': TREE });
    await screen.findByLabelText('按天看名额');
    expect(screen.queryByLabelText('补招')).toBeNull();
  });
});

describe('SCN-138 发单人改某一天的时段', () => {
  const POSTER = { ...ME, id: 9, nickname: '店主' };
  it('只列还能改的日子；填新时段，改完写明几个改了、几个要走变更单', async () => {
    const calls: Call[] = [];
    const tree = { ...TREE, by_day: [...TREE.by_day, { date: '2030-01-08', slots: 2, filled: 2, open: 0, done: 2, closed: 0 }] };
    open('/tasks/30', calls, { 'GET /tasks/30': PARENT, 'GET /tasks/30/tree': tree,
      'PATCH /tasks/30/days/2030-01-07/shift': { date: '2030-01-07', changed: [36], kept: [{ task_id: 35, reason: '已经有人接了' }], shift_start: '10:00', shift_end: '16:00' } }, POSTER);
    await screen.findByLabelText('改某天的时段');
    const select = screen.getByLabelText('改哪天的时段') as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(['2030-01-05', '2030-01-06', '2030-01-07']);
    fireEvent.change(select, { target: { value: '2030-01-07' } });
    fireEvent.change(screen.getByLabelText('这天几点开始'), { target: { value: '10:00' } });
    fireEvent.change(screen.getByLabelText('这天几点结束'), { target: { value: '16:00' } });
    fireEvent.click(screen.getByText('改这天的时段'));
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH' && c.path === '/tasks/30/days/2030-01-07/shift')?.body)
      .toEqual({ shift_start: '10:00', shift_end: '16:00' }));
    expect(await screen.findByText('01-07 改成 10:00–16:00：改了 1 个还在招的名额；1 个已经有人接了，改时间要和对方走合约变更单。')).toBeTruthy();
  });

  it('帮手看不到改时段', async () => {
    open('/tasks/30', [], { 'GET /tasks/30': PARENT, 'GET /tasks/30/tree': TREE });
    await screen.findByLabelText('按天看名额');
    expect(screen.queryByLabelText('改某天的时段')).toBeNull();
  });
});

describe('SCN-137 补招时顺带邀请', () => {
  const POSTER = { ...ME, id: 9, nickname: '店主' };
  it('勾上邀请：请求带 invite，结果写明邀了谁', async () => {
    const calls: Call[] = [];
    open('/tasks/30', calls, { 'GET /tasks/30': PARENT, 'GET /tasks/30/tree': TREE,
      'POST /tasks/30/days/2030-01-06/reboost': { date: '2030-01-06', slot_ids: [33, 34], raise_cents: 0, budget_cents: [1666, 1666],
        invited: [{ user_id: 5, nickname: '小王', task_id: 33 }] } }, POSTER);
    await screen.findByLabelText('补招');
    fireEvent.click(screen.getByLabelText('顺带邀请 3 个做过这类活、那天有空的人'));
    fireEvent.click(screen.getByText('补招这天'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path.endsWith('/reboost'))?.body).toEqual({ raise_cents: 0, invite: 3 }));
    expect(await screen.findByText('已补招 01-06：2 个还在招的名额再推了一次；邀请了 1 个那天有空、做过这类活的人（小王）。6 小时后可以再补一次。')).toBeTruthy();
  });
});
