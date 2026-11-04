/**
 * SPACE-024 / AI-DEC-021 合作驾驶舱的两端共用判断（368 号 spec，AI-DEC-021b）。
 *
 * 哪些预警要标红：两端原来各写一份 `dispute || overdue`，这次加了排期冲突，收成一处。
 */
import { formatDate, parseServerTime } from './time';
import type { Cockpit, CockpitAlert, CockpitNode, CockpitTimelineRow } from './types';

/** 要马上出手的预警：款项冻结、已逾期、排期排不开 */
export const URGENT_COCKPIT_ALERTS: ReadonlyArray<CockpitAlert['kind']> = [
  'dispute', 'overdue', 'schedule_conflict', 'past_parent_deadline',
  // AI-DEC-021c（384 号 spec）按工期估计赶不上截止
  'projected_late', 'estimate_past_deadline',
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

/** AI-DEC-021c（384 号 spec）时间线上一条：离最早开始的那一步多远、占多长（都是整段的百分比）。 */
export interface TimelineBar {
  task_id: number;
  offsetPct: number;
  widthPct: number;
  basis: CockpitTimelineRow['basis'];
  late: boolean;
  start: string;
  end: string;
}

/**
 * 把时间线排成能画的条：只画起止都有的步骤；整段从最早的开始画到最晚的结束。
 * 每条至少占 2%，一天的步骤在几个月的时间线上也看得见。字段缺失或畸形就少画，不报错。
 */
export function timelineBars(timeline: Cockpit['timeline'] | null | undefined): TimelineBar[] {
  const rows = Array.isArray(timeline?.rows) ? timeline!.rows : [];
  const ok = rows.flatMap((r) => {
    const s = parseServerTime(r?.start ?? null);
    const e = parseServerTime(r?.end ?? null);
    return r && typeof r.task_id === 'number' && s && e && e >= s ? [{ r, s: s.getTime(), e: e.getTime() }] : [];
  });
  if (!ok.length) return [];
  const lo = Math.min(...ok.map((x) => x.s));
  const span = Math.max(...ok.map((x) => x.e)) - lo || 1;
  return ok.map(({ r, s, e }) => {
    const offsetPct = Math.round(((s - lo) / span) * 1000) / 10;
    return {
      task_id: r.task_id, basis: r.basis, late: !!r.late, start: r.start!, end: r.end!, offsetPct,
      widthPct: Math.max(2, Math.min(100 - offsetPct, Math.round(((e - s) / span) * 1000) / 10)),
    };
  });
}

/** 时间线上方那一句：预计哪天做完；排不出来的说清是几步没填工期。没有时间线（老服务端）为空串 */
export function projectedFinishLine(cp: Pick<Cockpit, 'timeline'> | null | undefined, locale?: string): string {
  const t = cp?.timeline;
  if (!t || typeof t !== 'object') return '';
  const unknown = Array.isArray(t.unknown_steps) ? t.unknown_steps.length : 0;
  if (unknown) return `有 ${unknown} 步没填工期也没填截止，排不出整件事的完成日：给每一步填上要几天`;
  const d = formatDate(t.projected_finish ?? null, locale);
  return d ? `按各步工期排下来，预计 ${d} 做完` : '';
}

/** 一条的说明：「按工期 3 天」「没填工期，按截止排」「排不出来」，晚于自己截止的加一句 */
export function timelineBasisLabel(basis: CockpitTimelineRow['basis'] | string, late = false): string {
  const base = basis === 'estimate' ? '按工期估计' : basis === 'deadline' ? '没填工期，按截止排'
    : basis === 'done' ? '已完成' : '排不出来：没填工期也没填截止';
  return late ? `${base}（赶不上这一步的截止）` : base;
}
