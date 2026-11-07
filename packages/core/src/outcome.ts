/** OUT-052（444 号 spec）发单页上的「按结果计价」：把发布方填的东西变成服务端要的请求体，两端共用。
 *
 * 发布方填三样：交付说明里必须写明的关键词（每个变成一条平台判定指标）、加付上限（元），或者分档（通过几条、加付多少元）。
 * 规则都在服务端（递增、够得着、上限等于最高一档、不超过基础报酬……），这里只做两件事：
 * 把填写变成请求体；明显没填完的当场说清，不发一个注定被拒的请求。 */
import type { AcceptanceCriterionInput, BonusTier } from './types';

export interface OutcomeTierDraft {
  min_passed: string;
  yuan: string;
}

/** 关键词按逗号、顿号、换行拆开，去空、去重；每个变成「交付说明写明「X」」这样一条平台判定指标。 */
export function outcomeCriteria(keywords: string): AcceptanceCriterionInput[] {
  const words = [...new Set(keywords.split(/[,，、\n]/).map((x) => x.trim()).filter(Boolean))];
  return words.map((w) => ({ text: `交付说明写明「${w}」`, kind: 'auto' as const, check: { op: 'contains', value: w } }));
}

const cents = (yuan: string) => Math.round(parseFloat(yuan || '0') * 100);

export type OutcomePayload = { acceptance_criteria: AcceptanceCriterionInput[]; bonus_cents?: number; bonus_tiers?: BonusTier[] };

/** 返回请求体；没填完的返回 { error }（说清缺什么）。分档里整行空着的忽略，只填了一半的算没填完。 */
export function outcomePayload(input: { keywords: string; bonusYuan: string; tiers: OutcomeTierDraft[] }):
  OutcomePayload | { error: string } {
  const acceptance_criteria = outcomeCriteria(input.keywords);
  if (!acceptance_criteria.length) return { error: '按结果计价要写至少一个交付说明里必须写明的关键词：平台按它判定达标' };
  const rows = input.tiers.filter((t) => t.min_passed.trim() || t.yuan.trim());
  if (rows.some((t) => !t.min_passed.trim() || !t.yuan.trim())) return { error: '每一档都要写「通过几条」和「加付多少元」' };
  if (rows.length) {
    return {
      acceptance_criteria,
      bonus_tiers: rows.map((t) => ({ min_passed: parseInt(t.min_passed, 10) || 0, bonus_cents: cents(t.yuan) })),
    };
  }
  const bonus = cents(input.bonusYuan);
  if (bonus <= 0) return { error: '写一个加付上限（元），或者写分档' };
  return { acceptance_criteria, bonus_cents: bonus };
}
