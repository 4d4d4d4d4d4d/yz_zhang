/** APP-074e（439 号 spec）圈层的显示文案：两端共用，网页与 App 说法一致。 */
import type { CircleInfo } from './types';

export const CIRCLE_KIND_LABEL: Record<CircleInfo['kind'], string> = {
  interest: '兴趣圈',
  skill: '能力圈',
  local: '地域圈',
};

/** 还没加入时按钮上写什么；已加入或在等审核的没有按钮（null）。 */
export function circleJoinLabel(c: Pick<CircleInfo, 'my_status' | 'join_policy'>): string | null {
  if (c.my_status) return null;
  return c.join_policy === 'approval' ? '申请加入' : '加入圈层';
}

/** 圈层简介：有描述用描述，没有就写人数；有信用分门槛的写出来（不够的人加入时服务端会拦）。 */
export function circleSummary(c: Pick<CircleInfo, 'description' | 'member_count' | 'min_credit'>): string {
  const base = (c.description || '').trim() || `${Number(c.member_count) || 0} 位成员`;
  return c.min_credit > 0 ? `${base} · 信用分 ≥ ${c.min_credit}` : base;
}
