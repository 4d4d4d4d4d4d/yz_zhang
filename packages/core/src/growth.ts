// APP-074d（420 号 spec）通知开关的叫法、新人任务与邀请战绩的写法：网页与 App 共用一份。
import { fmtYuan } from './client';

/** 通知类目在界面上的叫法；没见过的新类目照原样显示，不吞掉 */
export const NOTIFICATION_PREF_LABEL: Record<string, string> = {
  task: '任务进展', system: '系统通知', interaction: '互动（评论、关注、私信）', assistant: '个人助手（例行任务与提醒）',
};
export const prefLabel = (category: string) => NOTIFICATION_PREF_LABEL[category] ?? category;

/** 「新人任务 2/5」；做完了或畸形时空串（不再占地方） */
export function newcomerLine(n: { finished?: unknown; total?: unknown; completed?: unknown } | null | undefined): string {
  if (!n || n.completed === true) return '';
  const f = typeof n.finished === 'number' ? n.finished : NaN;
  const t = typeof n.total === 'number' ? n.total : NaN;
  if (!Number.isFinite(f) || !Number.isFinite(t) || t <= 0) return '';
  return `新人任务 ${f}/${t}`;
}

/** 「已邀请 3 人 · 达成 1 人 · 累计奖励 ¥10.00」；畸形时空串 */
export function referralLine(r: { invited_count?: unknown; achieved_count?: unknown; earned_cents?: unknown } | null | undefined): string {
  if (!r) return '';
  const i = r.invited_count, a = r.achieved_count, e = r.earned_cents;
  if (typeof i !== 'number' || typeof a !== 'number' || typeof e !== 'number') return '';
  return `已邀请 ${i} 人 · 达成 ${a} 人 · 累计奖励 ${fmtYuan(e)}`;
}
