// LAW-060 / SCN-114 法律知识的运营草稿流（163 号 spec）：雷达起草、留空不能提交（服务端拒，界面原样说清）、四眼、出处。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = {
  id: 2, phone: '138****0002', nickname: '合规', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: true, credit_score: 100,
  rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2', admin_roles: ['compliance'],
};
const FAQ = (id: number, extra: Record<string, unknown> = {}) => ({
  id, topic: '婚姻家庭', keywords: ['离婚', '抚养'], answer: '【待填写】这里写', source: '【待填写】出处', status: 'draft',
  origin: 'radar:legal_gap:婚姻家庭', created_by: 2, reviewed_by: null, published_at: null, retired_reason: '',
  placeholders: ['回答', '出处'], updated_at: '2026-10-16T00:00:00Z', ...extra,
});
type Call = { method: string; path: string; body?: unknown };

function open(routes: Record<string, unknown>, calls: Call[], fail: Record<string, [number, string, string]> = {}) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const f = fail[`${method} ${p}`];
    if (f) return { ok: false, status: f[0], text: async () => JSON.stringify({ detail: { code: f[1], message: f[2] } }) };
    const key = Object.keys(routes).find((k) => k === `${method} ${p}`) ?? Object.keys(routes).find((k) => k === p);
    return { ok: true, status: 200, text: async () => JSON.stringify(key ? routes[key] : (p === '/users/me' ? ME : [])) };
  }) as unknown as typeof fetch;
  const client = new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={client}><App /></AppProvider></MemoryRouter>);
}

describe('LAW-060 法律知识运营', () => {
  it('雷达主题一键起草，编辑器打开草稿；留空提交被拒时把原因说清；写它的人不能自己批', async () => {
    const calls: Call[] = [];
    open({
      'GET /admin/legal/faqs': [FAQ(1), FAQ(2, { status: 'review', placeholders: [], answer: '已写好的回答内容', source: '《民法典》', created_by: 2 }),
        FAQ(3, { status: 'review', placeholders: [], answer: '已写好的回答内容', source: '《民法典》', created_by: 9, topic: '租房买房' })],
      '/admin/packs/radar': [{ source: 'legal_gap', key: '婚姻家庭', title: '「婚姻家庭」类法律问题常答不上', evidence: '近 30 天 3 个不同的人', people: 3, suggested: {} },
        { source: 'search_gap', key: '宠物', title: '搜了没有', evidence: 'x', people: 3, suggested: {} }],
      'POST /admin/legal/faqs/radar-draft': FAQ(4),
    }, calls, { 'POST /admin/legal/faqs/1/submit': [409, 'pack_placeholder_left', '回答、出处里还有「【待填写】」没填：写完再提交'] });
    const panel = await screen.findByLabelText('法律知识运营');
    await waitFor(() => expect(panel.textContent).toContain('回答、出处还没填'));
    expect(panel.textContent).not.toContain('搜了没有');
    fireEvent.click(screen.getByRole('button', { name: '起草法律知识' }));
    await waitFor(() => expect(calls.find((c) => c.path === '/admin/legal/faqs/radar-draft')?.body).toEqual({ topic: '婚姻家庭' }));
    expect(await screen.findByText(/已起草「婚姻家庭」.*【待填写】/)).toBeTruthy();
    expect(screen.getByText('编辑草稿 #4')).toBeTruthy();
    expect((screen.getByLabelText('回答') as HTMLTextAreaElement).value).toContain('【待填写】');
    fireEvent.click(screen.getAllByRole('button', { name: '提交审核' })[0]);
    expect(await screen.findByText(/【待填写】/, { selector: 'p.error' })).toBeTruthy();
    const approves = screen.getAllByRole('button', { name: '上线' }) as HTMLButtonElement[];
    expect(approves[0].disabled).toBe(true);
    expect(approves[1].disabled).toBe(false);
  });

  it('手写一条：关键词按逗号拆开', async () => {
    const calls: Call[] = [];
    open({ 'GET /admin/legal/faqs': [], 'POST /admin/legal/faqs': FAQ(5) }, calls);
    const panel = within(await screen.findByLabelText('法律知识运营'));
    fireEvent.change(panel.getByLabelText('关键词'), { target: { value: '押金，房东、退租' } });
    fireEvent.change(panel.getByLabelText('回答'), { target: { value: '押金一般在退租验房后返还，扣除要有约定和依据。' } });
    fireEvent.change(panel.getByLabelText('出处'), { target: { value: '《民法典》第七百二十二条' } });
    fireEvent.click(panel.getByRole('button', { name: '存为草稿' }));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/admin/legal/faqs')?.body).toEqual({
      topic: '', keywords: ['押金', '房东', '退租'], answer: '押金一般在退租验房后返还，扣除要有约定和依据。', source: '《民法典》第七百二十二条' }));
  });
});
