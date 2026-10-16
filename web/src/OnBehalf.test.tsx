// SCN-119 替别人发单（175 号 spec）：勾上「替别人发」才出现服务对象三项，并只在勾了时带进请求；详情页按可见性显示。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 2, phone: '138****0002', nickname: '女儿', bio: '', city: '上海', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2' };
type Call = { method: string; path: string; body?: unknown };
const TASK = (extra: Record<string, unknown>) => ({ id: 60, title: '装扶手', description: '', category: '维修', status: 'published', budget_cents: 20000,
  creator_id: 9, executor_id: null, is_remote: false, city: '上海', address_hint: '', address_exact: '', parent_id: null,
  task_type: 'service', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none', ...extra });

function open(path: string, calls: Call[], routes: Record<string, unknown> = {}) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const body = p in routes ? routes[p] : p === '/users/me' ? ME : p === '/categories' ? [{ name: '维修', required_cert: '' }]
      : p === '/cities' ? [{ id: 1, name: '上海' }] : method === 'POST' && p === '/tasks' ? { id: 61, title: '装扶手', status: 'published' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={[path]}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

const PUBLISH = '/publish?title=%E8%A3%85%E6%89%B6%E6%89%8B&category=%E7%BB%B4%E4%BF%AE&city=%E4%B8%8A%E6%B5%B7';

describe('SCN-119 替别人发单', () => {
  it('勾上才出现三项；请求带称呼、到场联系与「问过本人」', async () => {
    const calls: Call[] = [];
    open(PUBLISH, calls);
    await screen.findByDisplayValue('装扶手');
    expect(screen.queryByLabelText('服务对象称呼')).toBeNull();
    fireEvent.click(screen.getByLabelText('替别人发'));
    fireEvent.change(screen.getByLabelText('服务对象称呼'), { target: { value: '我妈' } });
    fireEvent.change(screen.getByLabelText('到场联系'), { target: { value: '王阿姨 139' } });
    fireEvent.click(screen.getByLabelText('已经问过本人'));
    fireEvent.change(screen.getByDisplayValue('— 请选择 —'), { target: { value: 'assign' } });
    fireEvent.submit(screen.getByLabelText('替别人发').closest('form')!);
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks')?.body).toMatchObject(
      { on_behalf: true, recipient_label: '我妈', onsite_contact: '王阿姨 139', recipient_consented: true }));
  });

  it('不勾就不带这几项（服务端对没勾却带了的会拒）', async () => {
    const calls: Call[] = [];
    open(PUBLISH, calls);
    await screen.findByDisplayValue('装扶手');
    fireEvent.change(screen.getByDisplayValue('— 请选择 —'), { target: { value: 'assign' } });
    fireEvent.submit(screen.getByLabelText('替别人发').closest('form')!);
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/tasks')).toBe(true));
    const body = calls.find((c) => c.method === 'POST' && c.path === '/tasks')!.body as Record<string, unknown>;
    expect('on_behalf' in body || 'recipient_label' in body || 'onsite_contact' in body).toBe(false);
  });

  it('详情页：别人只看到「替别人发的单」；成交双方看到称呼与到场联系', async () => {
    open('/tasks/60', [], { '/tasks/60': TASK({ on_behalf: true, recipient_label: '', onsite_contact: '' }) });
    expect((await screen.findByLabelText('服务对象')).textContent).toContain('服务对象与到场联系方式成交后可见');
  });

  it('详情页：成交双方看到称呼与到场联系', async () => {
    open('/tasks/60', [], { '/tasks/60': TASK({ on_behalf: true, recipient_label: '我妈', onsite_contact: '王阿姨 139', executor_id: 2 }) });
    const p = await screen.findByLabelText('服务对象');
    expect(p.textContent).toContain('服务对象「我妈」');
    expect(p.textContent).toContain('到场联系 王阿姨 139');
  });
});
