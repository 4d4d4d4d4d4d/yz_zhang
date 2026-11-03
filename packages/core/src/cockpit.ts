/**
 * SPACE-024 / AI-DEC-021 合作驾驶舱的两端共用判断（368 号 spec，AI-DEC-021b）。
 *
 * 哪些预警要标红：两端原来各写一份 `dispute || overdue`，这次加了排期冲突，收成一处。
 */
import type { CockpitAlert, CockpitNode } from './types';

/** 要马上出手的预警：款项冻结、已逾期、排期排不开 */
export const URGENT_COCKPIT_ALERTS: ReadonlyArray<CockpitAlert['kind']> = [
  'dispute', 'overdue', 'schedule_conflict', 'past_parent_deadline',
];

export function isUrgentCockpitAlert(a: { kind?: unknown } | null | undefined): boolean {
  return !!a && typeof a.kind === 'string' && (URGENT_COCKPIT_ALERTS as readonly string[]).includes(a.kind);
}

/** 截止那一格的补充说明：「（早于「设计稿」）」；没有冲突或字段缺失时为空串 */
export function scheduleConflictNote(node: Pick<CockpitNode, 'schedule_conflicts'> | null | undefined,
  title: (id: number) => string): string {
  const ids = Array.isArray(node?.schedule_conflicts) ? node!.schedule_conflicts.filter((i) => typeof i === 'number') : [];
  return ids.length ? `（不晚于要等的${ids.map((i) => `「${title(i)}」`).join('、')}）` : '';
}
