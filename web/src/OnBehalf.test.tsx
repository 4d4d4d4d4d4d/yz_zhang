// SCN-119 替别人发单（175 号 spec）：勾上「替别人发」才出现服务对象三项，并只在勾了时带进请求；详情页按可见性显示。
import { PlatformClient } from '@platform/core';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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

describe('SCN-123 发单后改服务对象', () => {
  const POSTER = { ...ME, id: 9 };
  function openAs(me: typeof ME, calls: Call[], task: Record<string, unknown>, patched?: Record<string, unknown>) {
    localStorage.setItem('token', 'tok');
    const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
      const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
      const method = init?.method ?? 'GET';
      calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
      const body = method === 'PATCH' && p === '/tasks/60/recipient' ? patched : p === '/tasks/60' ? task : p === '/users/me' ? me : [];
      return { ok: true, status: 200, text: async () => JSON.stringify(body) };
    }) as unknown as typeof fetch;
    render(<MemoryRouter initialEntries={['/tasks/60']}>
      <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
  }

  it('发单人改称呼与联系方式，要勾「已经问过本人」；保存后详情页显示新的', async () => {
    const calls: Call[] = [];
    const task = TASK({ on_behalf: true, recipient_label: '我妈', onsite_contact: '王阿姨 139' });
    openAs(POSTER, calls, task, { ...task, recipient_label: '我爸', onsite_contact: '李叔 138' });
    fireEvent.click(await screen.findByText('改服务对象'));
    fireEvent.change(screen.getByLabelText('服务对象怎么称呼'), { target: { value: '我爸' } });
    fireEvent.change(screen.getByLabelText('到场联系方式'), { target: { value: '李叔 138' } });
    fireEvent.click(screen.getByLabelText('已经问过本人'));
    fireEvent.click(screen.getByText('保存'));
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual(
      { recipient_label: '我爸', onsite_contact: '李叔 138', recipient_consented: true }));
    expect(await screen.findByText(/服务对象「我爸」/)).toBeTruthy();
    expect(screen.getByText(/已改好，接单的人会收到通知/)).toBeTruthy();
  });

  it('不是发单人、或单已结束：没有这个入口', async () => {
    openAs(ME, [], TASK({ on_behalf: true, recipient_label: '我妈', onsite_contact: '', executor_id: 2 }));
    await screen.findByLabelText('服务对象');
    expect(screen.queryByText('改服务对象')).toBeNull();
  });

  it('单已结束：没有这个入口', async () => {
    openAs(POSTER, [], TASK({ on_behalf: true, recipient_label: '我妈', onsite_contact: '', status: 'completed' }));
    await screen.findByLabelText('服务对象');
    expect(screen.queryByText('改服务对象')).toBeNull();
  });
});

describe('SCN-144 服务对象是未成年人', () => {
  it('勾上才出现安排方式与监护人确认；请求带这三项', async () => {
    const calls: Call[] = [];
    open(PUBLISH, calls);
    await screen.findByDisplayValue('装扶手');
    expect(screen.queryByLabelText('监护人在场')).toBeNull();
    fireEvent.click(screen.getByLabelText('服务对象是未成年人'));
    fireEvent.click(screen.getByLabelText('在公开场所'));
    fireEvent.click(screen.getByLabelText('我是监护人或已经监护人同意'));
    fireEvent.change(screen.getByDisplayValue('— 请选择 —'), { target: { value: 'assign' } });
    fireEvent.submit(screen.getByLabelText('服务对象是未成年人').closest('form')!);
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks')?.body).toMatchObject(
      { minor_involved: true, guardian_mode: 'public_place', guardian_consented: true }));
  });

  it('不勾不带；详情页写明安排方式与要求的证明', async () => {
    const calls: Call[] = [];
    open(PUBLISH, calls);
    await screen.findByDisplayValue('装扶手');
    fireEvent.change(screen.getByDisplayValue('— 请选择 —'), { target: { value: 'assign' } });
    fireEvent.submit(screen.getByLabelText('服务对象是未成年人').closest('form')!);
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/tasks')).toBe(true));
    expect('minor_involved' in (calls.find((c) => c.method === 'POST' && c.path === '/tasks')!.body as object)).toBe(false);
    cleanup();
    open('/tasks/60', [], { '/tasks/60': TASK({ minor_involved: true, guardian_mode: 'guardian_present' }) });
    expect((await screen.findByLabelText('未成年人服务')).textContent).toBe('服务对象是未成年人 · 监护人在场 · 接单要有平台审核通过的无犯罪记录证明');
  });
});
