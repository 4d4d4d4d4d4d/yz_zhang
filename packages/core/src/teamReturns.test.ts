// TEAM-070（226 号 spec）团队拨款退回的两句话。
import { describe, expect, it } from 'vitest';
import { teamReturnedNotice, teamReturnLine } from './teamReturns';

const R = { id: 5, team_id: 9, team_name: '某某科技', purpose: '活动物料', amount_cents: 8000, returned_cents: 0, returnable_cents: 8000, created_at: '' };

describe('TEAM-070 teamReturnLine / teamReturnedNotice', () => {
  it('写明哪个团队、哪笔、拨了多少、退过多少、还能退多少', () => {
    expect(teamReturnLine(R)).toBe('某某科技 · 支出 #5（活动物料）：拨给你 ¥80.00，最多还能退 ¥80.00');
    expect(teamReturnLine({ ...R, team_name: '', purpose: '', returned_cents: 3000, returnable_cents: 5000 }))
      .toBe('团队 #9 · 支出 #5：拨给你 ¥80.00，已退 ¥30.00，最多还能退 ¥50.00');
  });
  it('退完了说这笔结清了', () => {
    expect(teamReturnedNotice(3000, { id: 5, returned_cents: 3000, returnable_cents: 5000, available_cents: 0 })).toBe('已退回 ¥30.00，这笔还能退 ¥50.00');
    expect(teamReturnedNotice(5000, { id: 5, returned_cents: 8000, returnable_cents: 0, available_cents: 0 })).toBe('已退回 ¥50.00，这笔拨款已全部退清');
  });
});
