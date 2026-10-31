// KB-063b（326 号 spec）核验人写「没通过」的理由时就引导说具体：空话当场提醒，不拦提交；通过时不提醒。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 1, phone: '138****0000', nickname: '核验人', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0 };
const ORDER = { id: 5, task_id: 7, status: 'open', trigger: 'escalation', fee_cents: 3000, payer_id: -1, verifier_id: null,
  outcome: '', comment: '', revised_output: '', criteria_results: [], deadline: null, created_at: null };
const ROUTES: Record<string, unknown> = {
  '/users/me': ME,
  '/verification-orders': [{ ...ORDER, category: '保洁', task_title: '三居室保洁', claimable: true, reason: '' }],
  '/verification-orders/5/claim': { id: 5, status: 'claimed' },
  '/verification-orders/5/outcome': { outcome: 'rejected', unblocked: true, delivered: false },
  '/verification-orders/5': { ...ORDER, status: 'claimed', verifier_id: 1, task_title: '三居室保洁', task_description: '',
    category: '保洁', acceptance_criteria: [], agent_output: '产出', agent_confidence_bps: 5000, agent_criteria_results: [] },
};

async function open(calls: { method: string; path: string; body?: unknown }[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path, body: init?.body ? JSON.parse(init.body) : undefined });
    return { ok: true, status: 200, text: async () => JSON.stringify(ROUTES[path] ?? []) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/verify']}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
  await waitFor(() => expect(screen.getByText('接下')).toBeTruthy());
  fireEvent.click(screen.getByText('接下'));
  await waitFor(() => expect(screen.getByText('产出')).toBeTruthy());
}

describe('KB-063b 核验理由当场引导', () => {
  it('不通过时写空话：当场提醒，但照样能提交', async () => {
    const calls: { method: string; path: string; body?: unknown }[] = [];
    await open(calls);
    fireEvent.click(screen.getByLabelText('不通过'));
    const box = screen.getByPlaceholderText(/哪里不对、要怎么改/);
    fireEvent.change(box, { target: { value: '不行！！！！' } });
    expect(screen.getByTestId('vague-lesson').textContent).toContain('写具体些');
    fireEvent.change(box, { target: { value: '卫生间地漏没清，镜子有水印' } });
    expect(screen.queryByTestId('vague-lesson')).toBeNull();
    fireEvent.change(box, { target: { value: '质量差' } });
    fireEvent.click(screen.getByText('提交结论'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/verification-orders/5/outcome')?.body)
      .toEqual({ outcome: 'rejected', comment: '质量差', revised_output: '' }));
  });

  it('通过时不提醒', async () => {
    await open([]);
    fireEvent.change(screen.getByPlaceholderText('核验说明（发布方与平台都会看到）'), { target: { value: '好' } });
    expect(screen.queryByTestId('vague-lesson')).toBeNull();
  });
});
