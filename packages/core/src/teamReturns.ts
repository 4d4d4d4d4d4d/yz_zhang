// TEAM-070（226 号 spec）团队拨款退回：两端钱包页「团队拨款」同一句话。
import type { ReturnableTeamSpend, TeamSpendReturned } from './types';

const yuan = (c: number) => `¥${(c / 100).toFixed(2)}`;

export function teamReturnLine(r: ReturnableTeamSpend): string {
  return `${r.team_name || `团队 #${r.team_id}`} · 支出 #${r.id}${r.purpose ? `（${r.purpose}）` : ''}：拨给你 ${yuan(r.amount_cents)}`
    + (r.returned_cents > 0 ? `，已退 ${yuan(r.returned_cents)}` : '') + `，最多还能退 ${yuan(r.returnable_cents)}`;
}

/** 退成功后的提示；退完了说清楚这笔结清了 */
export function teamReturnedNotice(amountCents: number, r: TeamSpendReturned): string {
  return `已退回 ${yuan(amountCents)}` + (r.returnable_cents > 0 ? `，这笔还能退 ${yuan(r.returnable_cents)}` : '，这笔拨款已全部退清');
}

export const TEAM_RETURN_HINT = '钱划进你的钱包后和你自己的钱混在一起，平台分不出用掉了多少：请按实际没用完的退。';
