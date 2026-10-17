import type { TaskBrief } from './types';

/** SCN-110（194 号 spec）任务详情上的创作类需求九项。同一份数据，对不同的人换个说法：
 *  发单人自己看是「还可以补」；接单的人看是「报名前可以先问问发单人」——是该问的问题，不是挑发单人的错。
 *  九项都写到、或者不是创作类的单，返回 null（不显示）。两端同一个。 */
export function briefHint(brief: TaskBrief | null | undefined, isCreator: boolean): { title: string; lines: string[] } | null {
  if (!brief || !Array.isArray(brief.items)) return null;
  const missing = brief.items.filter((i) => !i.ok);
  if (missing.length === 0) return null;
  const total = brief.items.length;
  const title = isCreator
    ? `创作类需求一般写清九项，已写 ${total - missing.length}/${total}。还可以补：`
    : `说明里没写的 ${missing.length} 项，报名前可以先问问发单人：`;
  return { title, lines: missing.map((i) => `${i.name}：${i.ask}`) };
}
