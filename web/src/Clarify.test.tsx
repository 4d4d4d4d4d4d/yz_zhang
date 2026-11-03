// AI-DEC-001（366 号 spec）说一句话发单：发布页有入口；问答页把答过的带上再问，问清后带到发布页预填。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 2, phone: '138****0002', nickname: '我', bio: '', city: '上海', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2' };
type Call = { method: string; path: string; body?: Record<string, unknown> };
const DRAFT = { title: '家里要打扫一下', description: '家里要打扫一下\n地点：上海浦东', category: '保洁', is_remote: false, budget_cents: 30000, on_behalf_hint: false };

function open(path: string, calls: Call[], clarify: (body: Record<string, unknown>) => unknown) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    const body = init?.body ? JSON.parse(init.body) : undefined;
    calls.push({ method, path: p, body });
    const out = method === 'POST' && p === '/tasks/clarify' ? clarify(body) : p === '/users/me' ? ME
      : p === '/categories' ? [{ name: '保洁', required_cert: '' }] : p === '/cities' ? [{ id: 1, name: '上海' }] : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(out) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={[path]}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('AI-DEC-001 说一句话发单', () => {
  it('发布页有入口', async () => {
    open('/publish', [], () => ({}));
    fireEvent.click(await screen.findByText('💬 说一句话，帮我问清楚'));
    expect(await screen.findByLabelText('你要办什么事')).toBeTruthy();
  });

  it('答过的带上再问；问清后带到发布页，标题、类目、说明、预算都预填', async () => {
    const calls: Call[] = [];
    open('/publish/clarify', calls, (body) => {
      const answered = Object.keys((body.answers as Record<string, string>) || {});
      return answered.length
        ? { questions: [], draft: DRAFT, ready: true, blocked: null, remaining_required: 0 }
        : { questions: [{ key: 'where', ask: '在哪里做？', required: true, options: [] }], draft: { ...DRAFT, description: '家里要打扫一下' },
            ready: false, blocked: null, remaining_required: 1 };
    });
    fireEvent.change(await screen.findByLabelText('你要办什么事'), { target: { value: '家里要打扫一下' } });
    fireEvent.click(screen.getByText('开始'));
    expect((await screen.findByRole('status')).textContent).toContain('还差 1 件');
    fireEvent.change(screen.getByLabelText('在哪里做？'), { target: { value: '上海浦东' } });
    fireEvent.click(screen.getByText('回答'));
    await waitFor(() => expect(calls.filter((c) => c.path === '/tasks/clarify').length).toBe(2));
    expect(calls.filter((c) => c.path === '/tasks/clarify')[1].body).toEqual({ text: '家里要打扫一下', answers: { where: '上海浦东' }, category: '' });
    fireEvent.click(await screen.findByText('带到发布页'));
    expect(await screen.findByDisplayValue('家里要打扫一下')).toBeTruthy();
    expect(screen.getByDisplayValue('300')).toBeTruthy();
  });

  it('被拦下：说清原因，不给问题也不给「带到发布页」', async () => {
    open('/publish/clarify', [], () => ({ questions: [], draft: DRAFT, ready: false,
      blocked: { code: 'errand_restricted', message: '平台不承接代开处方药' }, remaining_required: 3 }));
    fireEvent.change(await screen.findByLabelText('你要办什么事'), { target: { value: '代开安眠药' } });
    fireEvent.click(screen.getByText('开始'));
    expect((await screen.findByRole('status')).textContent).toBe('平台不承接代开处方药');
    expect(screen.queryByText('带到发布页')).toBeNull();
  });
});

describe('AI-DEC-001 响应畸形', () => {
  it('回来的不是草稿：说清稍后再试，不白屏', async () => {
    open('/publish/clarify', [], () => ({ unexpected: true }));
    fireEvent.change(await screen.findByLabelText('你要办什么事'), { target: { value: '家里要打扫一下' } });
    fireEvent.click(screen.getByText('开始'));
    expect(await screen.findByText('助手暂时没回上来，请稍后再试')).toBeTruthy();
    expect(screen.getByLabelText('说一句话发单')).toBeTruthy();
  });
});
