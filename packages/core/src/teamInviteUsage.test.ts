// TEAM-068（228 号 spec）邀请链接使用记录的两句话。
import { describe, expect, it } from 'vitest';
import { INVITE_STATE_LABEL, inviteJoinedLine, memberSourceLabel } from './teamInviteUsage';

describe('TEAM-068 inviteJoinedLine / memberSourceLabel', () => {
  it('列出谁通过这条链接加入、离开的写明', () => {
    expect(inviteJoinedLine({ joined: [] })).toBe('');
    expect(inviteJoinedLine({})).toBe('');
    const line = inviteJoinedLine({ joined: [
      { user_id: 2, nickname: '小甲', joined_at: '2026-10-19T02:00:00Z', active: true },
      { user_id: 3, nickname: '', joined_at: '2026-10-19T02:00:00Z', active: false },
    ] });
    expect(line.startsWith('已加入：小甲（')).toBe(true);
    expect(line).toContain('2026');
    expect(line.endsWith('、用户 #3（已离开）')).toBe(true);
  });
  it('成员来源：手动加的与老服务端不写', () => {
    expect(memberSourceLabel({ invite_id: 7 })).toBe('通过邀请链接 #7 加入');
    expect(memberSourceLabel({ invite_id: null })).toBe('');
    expect(memberSourceLabel({})).toBe('');
  });
});

describe('TEAM-072 INVITE_STATE_LABEL', () => {
  it('四种状态都有中文名', () => {
    expect(INVITE_STATE_LABEL).toEqual({ active: '有效', used_up: '已用完', expired: '已过期', revoked: '已作废' });
  });
});
