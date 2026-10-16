// AI-DEC-040~048 逐层拆解树的共享文案与小工具（106 号 spec）。两端同一份，不各写各的。
import type { Decomposition, DecompositionNode, ExecutorKind, LeafCriterion, Task, TaskDaySummary, TaskVisits } from './types';

export const EXECUTOR_KIND_LABEL: Record<ExecutorKind, string> = {
  ai_closable: 'AI 可闭环',
  needs_human: '找人做',
  needs_expert: '需要持证专家',
  needs_machine: '需要设备',
  unknown: '待定：谁来做',
};

export const LEAF_CRITERION_LABEL: Record<LeafCriterion, string> = {
  deliverable: '交付物',
  acceptance: '验收标准',
  single_owner: '单一责任主体',
  budget: '可托管的预算',
};

/** 一步的执行主体标签。需要资质时说出是什么资质（「需要律师」比「需要专家」有用）。 */
export function executorLabel(node: DecompositionNode): string {
  if (!node.executor_kind) return '';
  if (node.executor_kind === 'needs_expert' && node.required_cert) return `需要${node.required_cert}`;
  return EXECUTOR_KIND_LABEL[node.executor_kind];
}

/** AI-DEC-048 拆解从哪来。**回落模板必须看得见**：模型不可用时界面要说出来。 */
export function decompositionSourceLabel(dec: Decomposition): string {
  if (dec.fallback) return 'AI 模型暂时不可用，以下按平台模板拆出';
  const s = dec.source;
  if (s.startsWith('anthropic:') || s === 'stub-model') return 'AI 逐层拆解';
  if (s === 'seed_template' || s === 'keyword_match') return '平台模板';
  if (s === 'closed_loop_experience') return '同类任务的成功经验';
  if (s === 'generic') return '通用三段式模板';
  return s || '—';
}

export function childrenOf(nodes: DecompositionNode[], parent: number | null): DecompositionNode[] {
  return nodes.filter((n) => n.parent === parent);
}

/** 没有子步骤的节点：要么是叶子，要么是还没拆完/停下来的步骤。 */
export function isOpenEnd(nodes: DecompositionNode[], node: DecompositionNode): boolean {
  return !nodes.some((n) => n.parent === node.id);
}

/** SCN-116 多天名额一天一行（174 号 spec）：「10-18 · 2 个名额：招到 1，还缺 1」。两端同一句话。 */
export function daySummaryLine(d: TaskDaySummary): string {
  const [, m, day] = d.date.split('-');
  const parts = [`招到 ${d.filled}`];
  parts.push(d.open > 0 ? `还缺 ${d.open}` : '不缺人了');
  if (d.done > 0) parts.push(`做完 ${d.done}`);
  if (d.closed > 0) parts.push(`取消 ${d.closed}`);
  return `${m}-${day} · ${d.slots} 个名额：${parts.join('，')}`;
}

/** 还缺人的那几天（按日期），给标题旁的一句提醒用；都招满了是空表。 */
export function daysStillShort(days: TaskDaySummary[] | undefined): TaskDaySummary[] {
  return (days ?? []).filter((d) => d.open > 0);
}

/** 详情页要不要拉子任务进度：项目型根任务（拆解出来的步骤），或多人、多天的母任务（名额）。两端同一条判断。 */
export function hasChildTasks(t: Pick<Task, 'parent_id' | 'task_type' | 'days' | 'people_needed'>): boolean {
  if (t.parent_id !== null) return false;
  return t.task_type === 'project' || (t.days ?? 1) > 1 || (t.people_needed ?? 1) > 1;
}

/** SCN-117 每天的时段一句话（178 号 spec）：多天的写「每天」，单天的只写时段；没写是空串。两端同一句。 */
export function shiftLabel(t: Pick<Task, 'shift_start' | 'shift_end' | 'days' | 'parent_id' | 'work_date'>): string {
  if (!t.shift_start || !t.shift_end) return '';
  const range = `${t.shift_start}–${t.shift_end}`;
  return (t.days ?? 1) > 1 ? `每天 ${range}` : `时段 ${range}`;
}

/** SCN-125 验收前的一句提醒（179 号 spec）：上门回报比计划少、或有没做的项时说清差多少；都齐了是空串。
 *  只是提醒，不拦验收——钱的事由发单人自己定。两端同一句。 */
export function visitShortfall(v: Pick<TaskVisits, 'planned' | 'reported' | 'missed_total'> | null | undefined): string {
  if (!v) return '';
  const parts: string[] = [];
  if (v.reported < v.planned) parts.push(`计划上门 ${v.planned} 次，回报了 ${v.reported} 次`);
  if (v.missed_total > 0) parts.push(`回报里一共有 ${v.missed_total} 项没做`);
  return parts.length ? `${parts.join('；')}。验收前可以先问问接单的人。` : '';
}

/** APP-090（182 号 spec）列表响应不是数组时当作空表：详情页的一块拿到 {} / null 不许把整页带崩。两端同一个。 */
export function asList<T>(x: unknown): T[] {
  return Array.isArray(x) ? (x as T[]) : [];
}
