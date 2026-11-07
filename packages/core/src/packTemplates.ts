import type { PackTaskTemplateBrief } from './types';

/** SCN-133（211 号 spec）用服务包的发单模板去发单时预填的东西：标题、类目、说明，带清单的再加上门次数与每次要做的事。
 *  只是预填，发不发由人决定（publish 关口）。两端同一份。 */
export function templatePrefill(t: PackTaskTemplateBrief): {
  title: string; category: string; description: string; visits: string; checklist: string;
} {
  const items = Array.isArray(t.visit_checklist) ? t.visit_checklist.filter((x) => typeof x === 'string' && x.trim()) : [];
  const n = Number(t.visits_planned) || 0;
  return { title: t.title, category: t.category, description: t.description,
    visits: n > 0 ? String(n) : '', checklist: items.join('、') };
}

/** 网页从服务包跳到发布页时的查询参数：没有清单的模板与以前一样只带三项。 */
export function templatePublishQuery(t: PackTaskTemplateBrief): string {
  const p = templatePrefill(t);
  const q = new URLSearchParams({ title: p.title, category: p.category, description: p.description });
  if (p.visits) q.set('visits', p.visits);
  if (p.checklist) q.set('checklist', p.checklist);
  return q.toString();
}
