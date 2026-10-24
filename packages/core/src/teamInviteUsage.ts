// TEAM-068（228 号 spec）邀请链接的使用记录：两端同一句话。
import { formatDate } from './time';
import type { TeamInviteLink } from './types';

/** 「已加入：小甲（10-19）、小乙（已离开）」；没人用过返回空串 */
export function inviteJoinedLine(link: Pick<TeamInviteLink, 'joined'>): string {
  const js = link.joined ?? [];
  if (!js.length) return '';
  return '已加入：' + js.map((j) => `${j.nickname || `用户 #${j.user_id}`}（${j.active ? formatDate(j.joined_at) : '已离开'}）`).join('、');
}

/** 成员从哪里来：通过邀请链接的写编号；所有者手动加的、老服务端没有这个字段的返回空串 */
export function memberSourceLabel(m: { invite_id?: number | null }): string {
  return m.invite_id ? `通过邀请链接 #${m.invite_id} 加入` : '';
}

/** TEAM-072（232 号 spec）链接状态的中文名（App 链接清单用；与 Web 团队页同一组词） */
export const INVITE_STATE_LABEL: Record<string, string> = { active: '有效', used_up: '已用完', expired: '已过期', revoked: '已作废' };
