/**
 * VER-050（372 号 spec）发单人点名核验人：两端共用的输入解析与说法。
 */

/** 输入框里的用户编号：空 → undefined（不点名，平台派单）；正整数 → 编号；其他 → null（填错了） */
export function parseVerifierId(input: string): number | undefined | null {
  const s = (input ?? '').trim();
  if (!s) return undefined;
  if (!/^\d{1,10}$/.test(s)) return null;
  const n = Number(s);
  return n >= 1 ? n : null;
}

/** 核验单是怎么来的（核验台与任务页共用） */
export function verifyTriggerLabel(trigger: string | null | undefined): string {
  switch (trigger) {
    case 'escalation': return '助理置信度不足，自动升级（平台付费）';
    case 'designated': return '发布方点名请你核验（发布方付费）';
    case 'requested': return '发布方主动申请核验';
    default: return '核验单';
  }
}

/** 候选一行：「小林 · 合作过 3 次」；不能点的带上原因（VER-050c，376 号 spec） */
export function verifierCandidateLine(c: { nickname?: string; user_id: number; times?: number; eligible?: boolean; reason?: string }): string {
  const name = c.nickname || `#${c.user_id}`;
  const times = typeof c.times === 'number' && c.times > 0 ? ` · 合作过 ${c.times} 次` : '';
  return c.eligible === false ? `${name}${times}（现在不能点：${c.reason || '资格不够'}）` : `${name}${times}`;
}

/** 点名前给发单人的一句话：谁付钱、对方要满足什么 */
export const DESIGNATE_VERIFIER_HINT =
  '可以点名一位你信得过的懂行的人（填对方的用户编号）：只有他能接，核验费由你付；对方要实名、不是本单当事人。不填就由平台派单。';
