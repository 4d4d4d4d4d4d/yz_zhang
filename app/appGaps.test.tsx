// APP-090 App 补齐（136 号 spec）：平台服务费发票、证据包导出（系统分享）、团队成员管理（TEAM-065）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, type TeamDetail } from '@platform/core';
import { Alert } from 'react-native';
import { EvidenceExportButton, InvoicesBlock, TeamMembersBlock } from './appGaps';

type Call = { method: string; path: string; body?: unknown };
function makeClient(routes: Record<string, unknown>, calls: Call[]) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : undefined });
    const hit = Object.keys(routes).find((k) => k === `${method} ${path}`) ?? Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}
const TEAM = {
  id: 9, name: '小团队', owner_id: 2, company_name: '', tax_number: '', verify_status: 'none', balance_cents: 0, my_role: 'owner',
  my_spend_limit_cents: 0, invoice_block: '', monthly_budget_cents: 0, month_spent_cents: 0, my_month_spent_cents: 0,
  members: [{ user_id: 2, role: 'owner', spend_limit_cents: 0, nickname: '我' }, { user_id: 5, role: 'member', spend_limit_cents: 50000, nickname: '小林' }],
} as unknown as TeamDetail;

describe('APP-090 App 补齐', () => {
  it('发票：按服务端口径提示，列出已申请的', async () => {
    const calls: Call[] = [];
    const client = makeClient({
      'GET /finance/invoices': [{ id: 1, kind: 'platform_fee', contract_id: 3, amount_cents: 1200, title: '某公司', status: 'requested', note: '', at: '2026-10-14T00:00:00Z' }],
      'POST /finance/invoices': { id: 2, scope_note: '只开平台佣金部分：¥12.00' },
    }, calls);
    render(<InvoicesBlock client={client} />);
    expect(await screen.findByText(/合约 #3 · ¥12.00 · 某公司/)).toBeTruthy();
    fireEvent.changeText(screen.getByLabelText('合约号'), '3');
    fireEvent.changeText(screen.getByLabelText('开票抬头'), '某公司');
    fireEvent.changeText(screen.getByLabelText('税号'), '91310000X');
    fireEvent.press(screen.getByText('申请开票'));
    expect(await screen.findByText('只开平台佣金部分：¥12.00')).toBeTruthy();
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ contract_id: 3, title: '某公司', tax_no: '91310000X' });
  });

  it('APP-076 合约卡片里的开票：合约号已填好、只列这一单', async () => {
    const calls: Call[] = [];
    const client = makeClient({
      'GET /finance/invoices': [
        { id: 1, kind: 'platform_fee', contract_id: 3, amount_cents: 1200, title: '某公司', status: 'requested', note: '', at: '2026-10-14T00:00:00Z' },
        { id: 5, kind: 'platform_fee', contract_id: 8, amount_cents: 900, title: '别的单', status: 'issued', note: '', at: '2026-10-14T00:00:00Z' },
      ],
      'POST /finance/invoices': { id: 2, scope_note: '只开平台佣金部分：¥12.00' },
    }, calls);
    render(<InvoicesBlock client={client} contractId={3} />);
    expect(await screen.findByText(/合约 #3 · ¥12.00/)).toBeTruthy();
    expect(screen.queryByText(/别的单/)).toBeNull();
    expect(screen.queryByLabelText('合约号')).toBeNull();
    fireEvent.changeText(screen.getByLabelText('开票抬头'), '某公司');
    fireEvent.press(screen.getByText('申请开票'));
    await screen.findByText('只开平台佣金部分：¥12.00');
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ contract_id: 3, title: '某公司', tax_no: '' });
  });

  it('证据包：整包原样交给系统分享（含证明力边界说明）', async () => {
    const pack = { package: { dispute_id: 4 }, sha256: 'ab', integrity: { chain_valid: true, chain_entries: 3 }, evidentiary_notice: '平台处理决定不是仲裁裁决' };
    const share = jest.fn(async () => undefined);
    render(<EvidenceExportButton client={makeClient({ '/legal/disputes/4/evidence-export': pack }, [])} disputeId={4} share={share} />);
    fireEvent.press(screen.getByText('导出证据包'));
    await waitFor(() => expect(share).toHaveBeenCalled());
    const arg = (share.mock.calls[0] as unknown as [{ message: string; title: string }])[0];
    expect(JSON.parse(arg.message)).toEqual(pack);
    expect(arg.title).toBe('纠纷 #4 证据包');
  });

  it('团队成员：所有者能加人、改角色、移出（先确认）；不是所有者只能看', async () => {
    const calls: Call[] = [];
    const onChanged = jest.fn();
    const client = makeClient({
      'POST /teams/9/members': { team_id: 9, user_id: 7, role: 'member', spend_limit_cents: 30000 },
      'PATCH /teams/9/members/5': { user_id: 5, role: 'admin', spend_limit_cents: 50000 },
      'DELETE /teams/9/members/5': { removed: 5 },
    }, calls);
    const alert = jest.spyOn(Alert, 'alert').mockImplementation((_t, _m, buttons) => { buttons?.[1]?.onPress?.(); });
    const { rerender } = render(<TeamMembersBlock client={client} teamId={9} team={TEAM} onChanged={onChanged} />);
    expect(screen.getByText('小林 · 成员 · 月度额度 ¥500.00')).toBeTruthy();
    fireEvent.press(screen.getByLabelText('切换角色：小林'));
    expect(await screen.findByText('角色已更新')).toBeTruthy();
    fireEvent.changeText(screen.getByLabelText('成员用户编号'), '7');
    fireEvent.changeText(screen.getByLabelText('月度额度'), '300');
    fireEvent.press(screen.getByText('加入团队'));
    expect(await screen.findByText('已加入')).toBeTruthy();
    fireEvent.press(screen.getByLabelText('移出：小林'));
    expect(await screen.findByText('已移出')).toBeTruthy();
    expect(calls.filter((c) => c.method !== 'GET').map((c) => [c.method, c.path, c.body])).toEqual([
      ['PATCH', '/teams/9/members/5', { role: 'admin' }],
      ['POST', '/teams/9/members', { user_id: 7, role: 'member', spend_limit_cents: 30000 }],
      ['DELETE', '/teams/9/members/5', undefined],
    ]);
    expect(onChanged).toHaveBeenCalledTimes(3);
    alert.mockRestore();
    rerender(<TeamMembersBlock client={client} teamId={9} team={{ ...TEAM, my_role: 'member' } as TeamDetail} onChanged={onChanged} />);
    expect(screen.getByText('只有团队所有者能管理成员。')).toBeTruthy();
    expect(screen.queryByText('加入团队')).toBeNull();
  });
});
