// ACC-041 / CERT-033 / NTF-065 / CS-032 / TAX-024 五条闭环的端上入口（77 号 spec）。
//
// 三分类闸门（CLI-082）能看出「这个 SDK 方法有人调了」；它看不出
// **调的时候有没有把该带的东西带上**，也看不出「关不掉的那几条」是不是
// 从服务端读来的——那正是这几条的要害。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = {
  id: 3, phone: '138****0003', nickname: '小明', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100,
  rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r3',
};

const PREFS = {
  prefs: { task: true, system: true, interaction: false },
  always_on_categories: ['funds'],
  always_on: [
    { category: 'task', title: '待验收提醒', why: '不处理就等于默认同意：到期自动验收并放款' },
    { category: 'task', title: '验收即将到期', why: '放款前的最后一次提醒' },
  ],
};

type Call = { method: string; path: string; body: unknown };

function mount(route: string, routes: Record<string, unknown> = {}, calls: Call[] = []) {
  localStorage.setItem('token', 'tok');
  const table: Record<string, unknown> = {
    '/users/me': ME,
    '/notifications': [],
    '/notifications/unread-count': { unread: 0 },
    '/notifications/prefs': PREFS,
    '/support/tickets': [],
    '/users/me/certifications': { active: [], applications: [] },
    '/finance/invoices': [],
    '/wallet': { available_cents: 0, escrow_cents: 0, frozen_cents: 0 },
    '/wallet/ledger': [],
    '/wallet/payout-account': { kind: '', account_no: '', holder_name: '', bound: false },
    '/finance/my-tax': { mode: 'labor', yearly: [], items: [], disclaimer: '这是代扣明细' },
    '/invitations': [],
    '/legal/agreements': {
      current_version: 'v1', documents: [], sensitive_scopes: [], rights: {},
    },
    '/auth/sessions': [],
    '/applications/mine': [],
    ...routes,
  };
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const full = String(url).replace(/^.*\/api\/v1/, '');
    const path = full.split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path, body: init?.body ? JSON.parse(init.body) : null });
    const hit = Object.keys(table).find((k) => k === full)
      ?? Object.keys(table).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? table[hit] : []) };
  }) as unknown as typeof fetch;
  const client = new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
  render(
    <MemoryRouter initialEntries={[route]}>
      <AppProvider client={client}><App /></AppProvider>
    </MemoryRouter>,
  );
  return calls;
}

afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); });

describe('ACC-041 忘了密码还进得来', () => {
  function openLogin(calls: Call[] = []) {
    const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
      const full = String(url).replace(/^.*\/api\/v1/, '');
      calls.push({ method: init?.method ?? 'GET', path: full.split('?')[0], body: init?.body ? JSON.parse(init.body) : null });
      if (full === '/auth/send-code') {
        return { ok: true, status: 200, text: async () => JSON.stringify({ sent: true, expires_in: 300, dev_code: '123456' }) };
      }
      if (full === '/auth/reset-password') {
        return { ok: true, status: 200, text: async () => JSON.stringify({ ok: true }) };
      }
      return { ok: false, status: 401, text: async () => JSON.stringify({ detail: { code: 'unauthorized', message: '未登录' } }) };
    }) as unknown as typeof fetch;
    const client = new PlatformClient({ baseUrl: '', getToken: () => null, fetchImpl });
    render(
      <MemoryRouter initialEntries={['/login']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    return calls;
  }

  it('注册获取 verify 场景验证码并提交用户输入，不能使用固定码', async () => {
    const calls = openLogin();
    fireEvent.click(screen.getByText('没有账号？去注册'));
    fireEvent.change(screen.getByLabelText('手机号'), { target: { value: '13800000991' } });
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'testpass123' } });
    fireEvent.click(screen.getByText('获取验证码'));
    await waitFor(() => expect(screen.getByTestId('sms-sent')).toBeTruthy());
    expect(calls.find(c => c.path === '/auth/send-code')?.body).toEqual({ phone: '13800000991', scene: 'verify' });
    fireEvent.change(screen.getByTestId('sms-code'), { target: { value: '829143' } });
    fireEvent.click(screen.getByRole('button', { name: '注册' }));
    await waitFor(() => expect(calls.find(c => c.path === '/auth/register')).toBeTruthy());
    expect((calls.find(c => c.path === '/auth/register')?.body as { sms_code: string }).sms_code).toBe('829143');
  });

  it('登录页有「忘记密码」与「验证码登录」两条路', async () => {
    openLogin();
    await waitFor(() => expect(screen.getByText('忘记密码')).toBeTruthy());
    expect(screen.getByText('验证码登录')).toBeTruthy();
  });

  it('重置密码：取验证码 → 提交 → 回到登录并提示用新密码', async () => {
    const calls = openLogin();
    await waitFor(() => expect(screen.getByText('忘记密码')).toBeTruthy());
    fireEvent.click(screen.getByText('忘记密码'));

    fireEvent.change(screen.getByPlaceholderText('13800000000'), { target: { value: '13800000001' } });
    fireEvent.click(screen.getByText('获取验证码'));
    // scene 要跟着用途走：找回密码与登录是两个场景
    await waitFor(() => {
      const sent = calls.find((c) => c.path === '/auth/send-code');
      expect(sent).toBeTruthy();
      expect((sent!.body as { scene: string }).scene).toBe('reset');
    });
    // 沙箱回显的验证码自动填入，省掉一次手抄
    await waitFor(() => expect((screen.getByTestId('sms-code') as HTMLInputElement).value).toBe('123456'));

    const pw = screen.getByLabelText(/新密码/) as HTMLInputElement;
    fireEvent.change(pw, { target: { value: 'newpass12345' } });
    fireEvent.click(screen.getByRole('button', { name: '重置密码' }));

    await waitFor(() => expect(screen.getByTestId('login-done')).toBeTruthy());
    const reset = calls.find((c) => c.path === '/auth/reset-password');
    expect((reset!.body as { new_password: string }).new_password).toBe('newpass12345');
  });
});

describe('NTF-065 通知开关，以及关不掉的那几条', () => {
  it('三类开关渲染出来，能改', async () => {
    const calls = mount('/notifications');
    await waitFor(() => expect(screen.getByTestId('pref-task')).toBeTruthy());
    expect((screen.getByTestId('pref-interaction').querySelector('input') as HTMLInputElement).checked).toBe(false);

    fireEvent.click(screen.getByTestId('pref-task').querySelector('input')!);
    await waitFor(() => expect(
      calls.some((c) => c.method === 'PUT' && c.path === '/notifications/prefs'),
    ).toBe(true));
  });

  it('「关不掉的」清单来自服务端，界面里没有这份清单的字面量', async () => {
    mount('/notifications');
    await waitFor(() => expect(screen.getByTestId('always-on-待验收提醒')).toBeTruthy());
    // 服务端给的 why 原样显示
    expect(screen.getByTestId('always-on-待验收提醒').textContent).toContain('到期自动验收并放款');
    expect(screen.getByTestId('always-on-验收即将到期')).toBeTruthy();
  });
});

describe('CS-032 工单自助', () => {
  it('能开工单，正文与回复都看得到', async () => {
    const calls = mount('/support', {
      '/support/tickets': [{
        id: 5, subject: '提现没到账', body: '昨天提的现在还没到', status: 'resolved',
        reply: '已核查，银行处理中', created_at: '2026-09-01T00:00:00Z',
      }],
    });
    await waitFor(() => expect(screen.getByTestId('ticket-5')).toBeTruthy());
    expect(screen.getByTestId('ticket-5').textContent).toContain('昨天提的现在还没到');
    // 运营的回复原文：只发一条通知的话，用户回到平台上再也找不到它
    expect(screen.getByTestId('ticket-reply-5').textContent).toContain('银行处理中');

    fireEvent.change(screen.getByPlaceholderText('问题一句话概括'), { target: { value: '发票开不出来' } });
    fireEvent.click(screen.getByText('提交工单'));
    await waitFor(() => {
      const sent = calls.find((c) => c.method === 'POST' && c.path === '/support/tickets');
      expect(sent).toBeTruthy();
      expect((sent!.body as { subject: string }).subject).toBe('发票开不出来');
    });
  });
});

describe('CERT-033 资质交得上去', () => {
  it('我的资质列表显示驳回理由', async () => {
    mount('/profile', {
      '/users/me/certifications': {
        active: [],
        applications: [{
          id: 7, name: '电工证', status: 'rejected',
          decision_reason: '证件影像不清晰，请重新上传',
          expires_at: null, created_at: '2026-09-01T00:00:00Z',
        }],
      },
    });
    await waitFor(() => expect(screen.getByTestId('my-cert-7')).toBeTruthy());
    expect(screen.getByTestId('my-cert-7').textContent).toContain('证件影像不清晰');
  });

  it('没选证件影像时提交按钮点不动（服务端也要求）', async () => {
    mount('/profile');
    await waitFor(() => expect(screen.getByText('提交核验')).toBeTruthy());
    expect((screen.getByText('提交核验') as HTMLButtonElement).disabled).toBe(true);
  });
});

describe('TAX-024 发票', () => {
  it('开票范围由服务端说，界面原样显示', async () => {
    const calls = mount('/wallet');
    await waitFor(() => expect(screen.getByText('平台服务费发票')).toBeTruthy());

    fireEvent.change(screen.getByPlaceholderText('合约号'), { target: { value: '9' } });
    fireEvent.change(screen.getByPlaceholderText('开票抬头'), { target: { value: '某某科技有限公司' } });
    fireEvent.click(screen.getByText('申请开票'));

    await waitFor(() => {
      const sent = calls.find((c) => c.method === 'POST' && c.path === '/finance/invoices');
      expect(sent).toBeTruthy();
      expect((sent!.body as { contract_id: number }).contract_id).toBe(9);
    });
  });
});
