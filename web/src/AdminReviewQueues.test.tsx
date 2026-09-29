// TEAM-031 / CERT-030/031 / UMOD-030 / CS-030 / SECEV-030 人审队列的出口（76 号 spec）。
//
// 源码扫描闸门能看出「`verifyTeam` 被调用了、组件挂上了」，它看不出
// **驳回时有没有真的把理由带上去**——而那正是这几条队列的要害：
// 「必须写」和「送到了」是两件事（V92 起反复出现的同一条）。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ADMIN = {
  id: 1, phone: '138****0001', nickname: '运营', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: true, credit_score: 100,
  rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r1',
};

const METRICS = {
  total_users: 10, verified_users: 8, total_tasks: 20, published_tasks: 3,
  completed_tasks: 12, closed_loop_rate: 0.6, dispute_count: 1,
  gmv_cents: 1000000, fee_income_cents: 80000,
};

const TEAM = {
  team_id: 4, name: '某某团队', owner_id: 7, owner_nickname: '老板',
  company_name: '某某科技有限公司', tax_number: '91310000MA1K00000X',
  license_urls: ['/api/v1/files/lic.png/secure'], created_at: '2026-09-01T00:00:00Z',
};

const CERT = {
  id: 12, user_id: 9, name: '电工证', holder_name: '张三', cert_number: 'C0001',
  issuer: '某市人社局', expires_at: '2027-01-01T00:00:00Z',
  image_urls: ['/api/v1/files/cert.png/secure'], real_name: '张三', name_matches: true,
  status: 'pending', created_at: '2026-09-01T00:00:00Z',
};

const APPROVED_CERT = { ...CERT, id: 13, status: 'approved' };

const UPLOAD = {
  name: 'p.png', url: '/api/v1/files/p.png', owner_id: 9, labels: ['可能含敏感内容'],
  content_type: 'image/png', size_bytes: 1234, created_at: '2026-09-01T00:00:00Z',
};

const TICKET = {
  id: 5, user_id: 9, subject: '提现没到账', body: '昨天提的现在还没到',
  created_at: '2026-09-01T00:00:00Z',
};

const BOARD = {
  banned: [{ ip: '203.0.113.7', seconds_left: 600, reason: '窗口内认证失败 5 次' }],
  watching: [], captcha_required_in_window: 2, threshold: 5, captcha_after: 3, ban_seconds: 900,
};

type Call = { method: string; path: string; body: unknown };

function openAdmin(routes: Record<string, unknown> = {}, calls: Call[] = []) {
  localStorage.setItem('token', 'tok');
  const table: Record<string, unknown> = {
    '/users/me': ADMIN,
    '/admin/metrics': METRICS,
    '/admin/reports': [],
    '/admin/users': [],
    '/wallet/withdraw-requests?status=pending': [],
    '/wallet/withdraw-requests?status=awaiting_second': [],
    '/admin/aml/activities': { items: [], note: '' },
    '/admin/audit-log': [],
    '/admin/platform-finance': { balance_cents: 0, total_fee_cents: 0, settled_cents: 0, fee_count: 0 },
    '/admin/teams/pending': [],
    '/admin/certifications/pending': [],
    '/admin/certifications': [],
    '/admin/uploads/pending': [],
    '/admin/tickets': [],
    '/admin/security': { ...BOARD, banned: [] },
    '/cities': [],
    '/categories': [],
    ...routes,
  };
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const full = String(url).replace(/^.*\/api\/v1/, '');
    const path = full.split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path, body: init?.body ? JSON.parse(init.body) : null });
    // 先按「路径 + 查询串」精确匹配，再退回只看路径——
    // 否则 ?status=pending 与 ?status=approved 会拿到同一份数据
    const hit = Object.keys(table).find((k) => k === full)
      ?? Object.keys(table).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? table[hit] : []) };
  }) as unknown as typeof fetch;
  const client = new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
  render(
    <MemoryRouter initialEntries={['/admin']}>
      <AppProvider client={client}><App /></AppProvider>
    </MemoryRouter>,
  );
  return calls;
}

afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); });

describe('TEAM-031 团队企业信息核验', () => {
  it('待核验的团队列得出来，执照影像是鉴权 URL', async () => {
    openAdmin({ '/admin/teams/pending': [TEAM] });
    await waitFor(() => expect(screen.getByTestId('team-verify-4')).toBeTruthy());
    const card = screen.getByTestId('team-verify-4');
    expect(card.textContent).toContain('某某科技有限公司');
    expect(card.textContent).toContain('老板');
    // 营业执照是企业敏感材料：不能是匿名能力 URL
    expect(card.querySelector('a')?.getAttribute('href')).toContain('/secure');
  });

  it('核验通过会把请求发出去', async () => {
    const calls = openAdmin({ '/admin/teams/pending': [TEAM] });
    await waitFor(() => expect(screen.getByTestId('team-verify-4')).toBeTruthy());
    fireEvent.click(screen.getByText('核验通过'));
    await waitFor(() => expect(
      calls.some((c) => c.method === 'POST' && c.path === '/admin/teams/4/verify'),
    ).toBe(true));
  });

  it('驳回必须带上理由，理由为空就不发请求', async () => {
    const calls = openAdmin({ '/admin/teams/pending': [TEAM] });
    await waitFor(() => expect(screen.getByTestId('team-verify-4')).toBeTruthy());

    vi.spyOn(window, 'prompt').mockReturnValue('   ');
    fireEvent.click(screen.getByText('驳回'));
    await waitFor(() => expect(screen.getByTestId('team-verify-4')).toBeTruthy());
    expect(calls.some((c) => c.method === 'POST' && c.path === '/admin/teams/4/verify')).toBe(false);

    vi.spyOn(window, 'prompt').mockReturnValue('执照影像模糊');
    fireEvent.click(screen.getByText('驳回'));
    await waitFor(() => {
      const sent = calls.find((c) => c.method === 'POST' && c.path === '/admin/teams/4/verify');
      expect(sent).toBeTruthy();
      expect((sent!.body as { reason: string }).reason).toBe('执照影像模糊');
    });
  });
});

describe('CERT-030/031 资质核验与撤销', () => {
  it('姓名是否一致读服务端算好的字段，界面不自己比', async () => {
    openAdmin({ '/admin/certifications/pending': [{ ...CERT, name_matches: false }] });
    await waitFor(() => expect(screen.getByTestId('cert-12')).toBeTruthy());
    expect(screen.getByTestId('cert-12').textContent).toContain('姓名不一致');
  });

  it('已核准的资质能撤销（此前这个端点没有任何入口）', async () => {
    const calls = openAdmin({ '/admin/certifications?status=approved&limit=50': [APPROVED_CERT] });
    await waitFor(() => expect(screen.getByTestId('cert-approved-13')).toBeTruthy());

    vi.spyOn(window, 'prompt').mockReturnValue('证件经复核为伪造');
    fireEvent.click(screen.getByText('撤销'));
    await waitFor(() => {
      const sent = calls.find((c) => c.method === 'POST' && c.path === '/admin/certifications/13/revoke');
      expect(sent).toBeTruthy();
      expect((sent!.body as { reason: string }).reason).toBe('证件经复核为伪造');
    });
  });
});

describe('UMOD-030 / CS-030 / SECEV-030', () => {
  it('图片人审队列能处置，界面说清移除会通知上传者', async () => {
    const calls = openAdmin({ '/admin/uploads/pending': [UPLOAD] });
    await waitFor(() => expect(screen.getByTestId('upload-p.png')).toBeTruthy());
    expect(screen.getByText(/悄悄删掉/)).toBeTruthy();

    vi.spyOn(window, 'prompt').mockReturnValue('含违规内容');
    fireEvent.click(screen.getByText('移除'));
    await waitFor(() => expect(
      calls.some((c) => c.method === 'POST' && c.path === '/admin/uploads/p.png/resolve'),
    ).toBe(true));
  });

  it('工单能回复，空回复不发请求', async () => {
    const calls = openAdmin({ '/admin/tickets': [TICKET] });
    await waitFor(() => expect(screen.getByTestId('ticket-5')).toBeTruthy());

    vi.spyOn(window, 'prompt').mockReturnValue('');
    fireEvent.click(screen.getByText('回复并结单'));
    await waitFor(() => expect(screen.getByTestId('ticket-5')).toBeTruthy());
    expect(calls.some((c) => c.path === '/admin/tickets/5/resolve')).toBe(false);

    vi.spyOn(window, 'prompt').mockReturnValue('银行处理中');
    fireEvent.click(screen.getByText('回复并结单'));
    await waitFor(() => {
      const sent = calls.find((c) => c.path === '/admin/tickets/5/resolve');
      expect(sent).toBeTruthy();
      expect((sent!.body as { reply: string }).reply).toBe('银行处理中');
    });
  });

  it('被封的 IP 能解封，阈值取自服务端而不是界面写死', async () => {
    const calls = openAdmin({ '/admin/security': BOARD });
    await waitFor(() => expect(screen.getByText('203.0.113.7')).toBeTruthy());
    expect(screen.getByText('5 次 / 900s')).toBeTruthy();

    fireEvent.click(screen.getByText('解封'));
    await waitFor(() => {
      const sent = calls.find((c) => c.path === '/admin/security/unban');
      expect(sent).toBeTruthy();
      expect((sent!.body as { ip: string }).ip).toBe('203.0.113.7');
    });
  });
});
