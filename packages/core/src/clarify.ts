/** AI-DEC-001（366 号 spec）对话式需求澄清：两端共用的草稿转换与进度文案。 */
import type { ClarifyDraft, ClarifyResult, PackTaskTemplateBrief } from './types';

/** 澄清出的草稿 → 发布页能吃的模板（App 走 PublishScreen 的 template，网页走查询参数） */
export function clarifyTemplate(d: ClarifyDraft): PackTaskTemplateBrief {
  return { key: 'clarify', title: d.title, category: d.category, description: d.description, visits_planned: 0, visit_checklist: [] };
}

/** 网页跳到发布页的查询参数：标题、类目、说明，有预算再带预算（元） */
export function clarifyPublishQuery(d: ClarifyDraft): string {
  const q = new URLSearchParams({ title: d.title, category: d.category, description: d.description });
  if (d.budget_cents && d.budget_cents > 0) q.set('budget', String(d.budget_cents / 100));
  return q.toString();
}

/** 一行说清还差几问 */
export function clarifyProgressLine(r: ClarifyResult): string {
  if (r.blocked) return r.blocked.message;
  if (r.ready) return r.questions.length ? '必答的都清楚了，可以带到发布页；下面这些选答也能帮接单的人报价' : '都问清楚了，可以带到发布页';
  return `还差 ${r.remaining_required} 件要问清楚`;
}
