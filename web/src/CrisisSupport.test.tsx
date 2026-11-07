// SCN-172（299 号 spec）私聊里写下想伤害自己的话：消息照常发出，只给发送的人在输入框上方显示心理援助热线。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 1, phone: '138****0001', nickname: '我', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r1' };
const HOTLINE = '如果你或身边的人现在有伤害自己的念头，请马上拨打 12356 全国心理援助热线';

function open(reply: Record<string, unknown>, sent: string[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    if (method === 'POST' && path === '/conversations/5/messages') sent.push(JSON.parse(init?.body ?? '{}').content);
    const body = path === '/users/me' ? ME
      : path === '/conversations' ? [{ id: 5, kind: 'direct', task_id: null, participants: [1, 2] }]
      : path === '/conversations/5/messages' ? (method === 'POST' ? reply : []) : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/messages?conversation=5']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('SCN-172 私聊里的热线', () => {
  it('服务端给了 support 时显示在输入框上方；消息照常发出', async () => {
    const sent: string[] = [];
    open({ id: 9, risk_flagged: false, warning: null, support: HOTLINE }, sent);
    fireEvent.change(await screen.findByPlaceholderText('输入消息…'), { target: { value: '不想活了' } });
    fireEvent.click(screen.getByText('发送'));
    expect((await screen.findByTestId('crisis-support')).textContent).toBe(HOTLINE);
    expect(sent).toEqual(['不想活了']);
  });

  it('普通消息不显示', async () => {
    const sent: string[] = [];
    open({ id: 9, risk_flagged: false, warning: null }, sent);
    fireEvent.change(await screen.findByPlaceholderText('输入消息…'), { target: { value: '明天见' } });
    fireEvent.click(screen.getByText('发送'));
    await waitFor(() => expect(sent).toEqual(['明天见']));
    expect(screen.queryByTestId('crisis-support')).toBeNull();
  });
});
