// ADMIN-062 审计日志防篡改：后台「校验完整性」（149 号 spec）。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ADMIN = { id: 1, phone: '138****0001', nickname: '合规', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['compliance'], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r1' };

function open(report: unknown) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const body: unknown = path === '/users/me' ? ADMIN
      : path === '/admin/audit-log/verify' ? report
      : path === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('ADMIN-062 审计完整性', () => {
  it('完整：说清走了多少条、最新一条，并单列不在链上的旧记录', async () => {
    open({ ok: true, checked: 42, head_hash: 'a'.repeat(64), head_audit_id: 99, legacy_unchained: 7, problems: [] });
    fireEvent.click(await screen.findByText('校验完整性'));
    const box = await screen.findByLabelText('审计完整性');
    expect(box.textContent).toContain('链上 42 条逐条对得上');
    expect(box.textContent).toContain('#99');
    expect(box.textContent).toContain('7 条是启用哈希链之前的旧记录');
  });

  it('有断点：逐条列出编号与原因，并说怎么办', async () => {
    open({ ok: false, checked: 10, head_hash: 'b'.repeat(64), head_audit_id: 12, legacy_unchained: 0,
      problems: [{ audit_id: 5, reason: '内容与哈希对不上：这一条被改过' }, { audit_id: 12, reason: '链头记的最新一条与实际不符：最后几条被删了' }] });
    fireEvent.click(await screen.findByText('校验完整性'));
    const box = await screen.findByLabelText('审计完整性');
    expect(box.textContent).toContain('保留现场');
    const items = within(box).getAllByRole('listitem').map((li) => li.textContent);
    expect(items).toEqual(['#5：内容与哈希对不上：这一条被改过', '#12：链头记的最新一条与实际不符：最后几条被删了']);
  });
});
