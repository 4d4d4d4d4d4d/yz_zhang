// SCN-219（336 号 spec）被发单拦截挡下时申请人工复核：发布页挡下后出现申请框，原样带上标题与说明；
// 后台列出在等的，通过或维持（维持要写理由）；自己提出的不给处理按钮。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const USER = { id: 2, phone: '138****0002', nickname: '我', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [],
  credit_level: '普通', referral_code: 'r2', weekly_slots: [], limited_capacity: false };
const OPS = { ...USER, id: 3, nickname: '运营', is_admin: true, admin_roles: ['ops'] };
const ROW = { id: 5, kind: 'ghostwrite', kind_label: '代写学位论文代考', title: '论文集出版宣传', description: '写推介文案',
  explanation: '是宣传文案不是代写论文', status: 'pending', decision_note: '', task_id: null,
  created_at: '2026-10-30T00:00:00Z', decided_at: null, user_id: 9, nickname: '小王', waited_hours: 2, sla_hours: 24, overdue: false };
type Call = { method: string; path: string; body?: Record<string, unknown> };

function open(path: string, me: object, calls: Call[], extra: (method: string, p: string) => unknown = () => undefined) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    if (method === 'POST' && p === '/tasks') {
      return { ok: false, status: 400, headers: { get: () => null },
        text: async () => JSON.stringify({ detail: { code: 'academic_ghostwriting', message: '平台不承接代写学位论文', review: 'errand_review' } }) };
    }
    const hit = extra(method, p);
    const body = hit !== undefined ? hit : p === '/users/me' ? me : p === '/categories' ? [{ id: 1, name: '文案写作', required_cert: '' }]
      : p === '/admin/admins' ? { admins: [] } : p === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, headers: { get: () => null }, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={[path]}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('SCN-219 发单复核', () => {
  it('发布被拦下：出现「申请人工复核」，原样带上标题与说明，写够一句话才能交', async () => {
    const calls: Call[] = [];
    open('/publish', USER, calls, (m, p) => (m === 'POST' && p === '/tasks/errand-reviews' ? { ...ROW, user_id: undefined } : undefined));
    const title = await screen.findByLabelText('标题', {}, { timeout: 3000 });
    fireEvent.change(title, { target: { value: '论文集出版宣传' } });
    fireEvent.change(screen.getByLabelText('描述'), { target: { value: '写推介文案' } });
    await screen.findByRole('option', { name: '文案写作' });
    fireEvent.change(screen.getByLabelText('类目'), { target: { value: '文案写作' } });
    fireEvent.click(screen.getByLabelText(/线上任务/));
    fireEvent.submit(title.closest('form')!);
    fireEvent.click(await screen.findByText('觉得拦错了？申请人工复核'));
    const box = screen.getByLabelText('申请人工复核');
    const send = within(box).getByText('提交复核');
    fireEvent.change(within(box).getByLabelText('复核说明'), { target: { value: '误拦' } });
    expect((send as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(within(box).getByLabelText('复核说明'), { target: { value: '是宣传文案不是代写论文' } });
    fireEvent.click(send);
    await screen.findByText(/已申请复核/);
    const req = calls.find((c) => c.method === 'POST' && c.path === '/tasks/errand-reviews')!;
    expect(req.body).toEqual({ title: '论文集出版宣传', description: '写推介文案', explanation: '是宣传文案不是代写论文' });
  });

  it('后台：通过不用写理由；维持要写够理由；自己提出的不给按钮', async () => {
    const calls: Call[] = [];
    open('/admin', OPS, calls, (m, p) => (m === 'GET' && p === '/admin/errand-reviews'
      ? [ROW, { ...ROW, id: 6, title: '我自己发的', user_id: 3, waited_hours: 30, overdue: true }]
      : p.startsWith('/admin/errand-reviews/') ? ROW : undefined));
    const box = await screen.findByLabelText('发单复核', {}, { timeout: 3000 });
    expect(box.textContent).toContain('是宣传文案不是代写论文');
    const own = within(box).getByText('我自己发的').closest('li')!;
    expect(within(own).queryByText('通过')).toBeNull();
    expect(within(own).getByText('已超 24 小时')).toBeTruthy();   // SCN-220 超过时限的标出来
    expect(within(box).getAllByText(/已超/)).toHaveLength(1);
    const row = within(box).getByText('论文集出版宣传').closest('li')!;
    const keep = within(row).getByText('维持拦截') as HTMLButtonElement;
    expect(keep.disabled).toBe(true);
    fireEvent.change(within(row).getByLabelText('复核 5 的说明'), { target: { value: '就是代写论文' } });
    expect(keep.disabled).toBe(false);
    fireEvent.click(keep);
    await waitFor(() => expect(calls.some((c) => c.path === '/admin/errand-reviews/5/reject')).toBe(true));
    expect(calls.find((c) => c.path === '/admin/errand-reviews/5/reject')!.body).toEqual({ note: '就是代写论文' });
    fireEvent.click(within(row).getByText('通过'));
    await waitFor(() => expect(calls.some((c) => c.path === '/admin/errand-reviews/5/approve')).toBe(true));
  });
});
