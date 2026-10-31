import { fmtYuan } from './client';
import { hasChildTasks } from './decompose';
import type { ReboostDayResult, Task, TaskReboostResult } from './types';

/** SCN-121（196 号 spec）补招之后的一句话：哪天、几个名额再推了一次、加了多少。两端同一句。 */
export function reboostLine(r: Pick<ReboostDayResult, 'date' | 'slot_ids' | 'raise_cents' | 'invited'>, askedInvite = false): string {
  const n = Array.isArray(r.slot_ids) ? r.slot_ids.length : 0;
  const extra = r.raise_cents > 0 ? `，每个名额加价 ${fmtYuan(r.raise_cents)}` : '';
  // SCN-137 顺带邀请了谁：写人数与昵称；勾了却没找到合适的人也说一声
  const invited = Array.isArray(r.invited) ? r.invited : [];
  const who = invited.length
    ? `；邀请了 ${invited.length} 个那天有空、做过这类活的人（${invited.map((x) => x.nickname).join('、')}）`
    : askedInvite ? '；这天没找到做过这类活、又正好有空的人可邀' : '';
  return `已补招 ${String(r.date).slice(5)}：${n} 个还在招的名额再推了一次${extra}${who}。6 小时后可以再补一次。`;
}

/** 补招表单里「每个名额加价（元）」的输入换成分：空着是 0（只再推一次）；不是正数返回 null（表单提示）。 */
export function raiseToCents(yuan: string): number | null {
  const t = yuan.trim();
  if (!t) return 0;
  if (!/^\d+(\.\d{1,2})?$/.test(t)) return null;
  return Math.round(Number(t) * 100);
}

/** SCN-137 两端补招时勾「顺带邀请」一次邀几个人（服务端上限 5）。 */
export const REBOOST_INVITE_COUNT = 3;

/** AI-DEC-023（320 号 spec）没人报名的单再推一次之后的一句话。两端同一句。 */
export function taskReboostLine(r: Pick<TaskReboostResult, 'raise_cents' | 'budget_cents'>): string {
  const extra = r.raise_cents > 0 ? `，加价 ${fmtYuan(r.raise_cents)}（现在预算 ${fmtYuan(r.budget_cents)}）` : '';
  return `已再推一次${extra}：会推给附近有空、订阅了这个类目的人。6 小时后可以再推。`;
}

/** AI-DEC-023 什么时候给发单人「再推一次」：还在招、没人接、一个报名都没有；
 * 带子任务的母任务（项目、一单多人或多天）不给——报名都在名额、子任务上，按天补招或在子任务上推。 */
export function canReboostTask(t: Pick<Task, 'status' | 'executor_id' | 'parent_id' | 'days' | 'people_needed' | 'task_type'>, applications: number): boolean {
  if (t.status !== 'published' || t.executor_id !== null || applications > 0) return false;
  return !hasChildTasks(t);
}
