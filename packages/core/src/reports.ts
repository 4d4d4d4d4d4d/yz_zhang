/**
 * RISK-010~014（399 号 spec，V426）举报的两端共用说法。
 *
 * 类型的顺序与服务端 `REPORT_CATEGORIES` 一致，两端下拉框按这个顺序排；
 * 处理结果只说结果，不说是哪位审核员。
 */
import type { MyReport, ReportCategory, ReportSubmitResult, ReportTarget } from './types';

export const REPORT_CATEGORY_OPTIONS: ReadonlyArray<{ value: ReportCategory; label: string }> = [
  { value: 'illegal', label: '违法违规' },
  { value: 'porn', label: '色情低俗' },
  { value: 'fraud', label: '诈骗或骗钱' },
  { value: 'harassment', label: '骚扰或辱骂' },
  { value: 'infringement', label: '侵犯权益（抄袭、冒用、泄露隐私）' },
  { value: 'other', label: '其他' },
];

const TARGETS: Record<ReportTarget, string> = { task: '任务', content: '内容', user: '用户', message: '私信' };

export function reportCategoryLabel(c: unknown): string {
  return REPORT_CATEGORY_OPTIONS.find((o) => o.value === c)?.label ?? '其他';
}

export function reportTargetLabel(t: unknown): string {
  return (typeof t === 'string' && (TARGETS as Record<string, string>)[t]) || '对象';
}

/** 提交以后给举报人的一句话：重复举报要说清「已经在处理」，不让人以为又提交了一次。 */
export function reportSubmittedNote(r: Partial<ReportSubmitResult> | null | undefined): string {
  if (r && r.duplicate) return '你已经举报过它，还在处理中；处理完会通知你';
  return '已提交，审核员会尽快处理，处理完会通知你；结果可以在「我的举报」里看';
}

/** RISK-016（401 号 spec）处置队列里一行的时限：「已等 5 小时（24 小时内处理）」，超了写「已超时」。字段缺了不显示。 */
export function reportSlaLine(r: { waited_hours?: unknown; sla_hours?: unknown; overdue?: unknown } | null | undefined): string {
  if (!r || typeof r.waited_hours !== 'number' || typeof r.sla_hours !== 'number') return '';
  return `已等 ${r.waited_hours} 小时（${r.sla_hours} 小时内处理）${r.overdue ? ' · 已超时' : ''}`;
}

/** 「我的举报」里一行的状态：处理中，或处理结果。 */
export function reportStatusLine(r: Pick<MyReport, 'status' | 'result'> | null | undefined): string {
  if (!r || r.status !== 'resolved') return '处理中';
  return `已处理：${r.result || '已处理'}`;
}
