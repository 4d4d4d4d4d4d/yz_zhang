/** SCN-219（336 号 spec）被发单拦截挡下时申请人工复核：两端共用的判断与文案。 */
import type { ErrandReviewItem } from './types';

/** 这几类拦截只看文字、会误拦：挡下时给「申请人工复核」。金融、学科类家教这类业务红线不在其中。 */
export const ERRAND_REVIEW_CODES = [
  'errand_restricted', 'unlicensed_driving_practice', 'academic_ghostwriting', 'fake_review', 'fake_traffic',
  // SCN-231（342 号 spec）、SCN-234（344 号 spec）
  'fake_inspection', 'voice_clone',
  // SCN-243（351 号 spec）
  'odometer_fraud',
] as const;

export const ERRAND_REVIEW_MIN_EXPLANATION = 6;

export function canRequestErrandReview(code: string | null | undefined): boolean {
  return !!code && (ERRAND_REVIEW_CODES as readonly string[]).includes(code);
}

export const ERRAND_REVIEW_STATUS_LABEL: Record<ErrandReviewItem['status'], string> = {
  pending: '等运营复核',
  approved: '已通过',
  rejected: '维持拦截',
};

/** 一行说清这条复核现在怎样、下一步做什么 */
export function errandReviewLine(r: ErrandReviewItem): string {
  const head = `「${r.title}」${ERRAND_REVIEW_STATUS_LABEL[r.status] ?? r.status}`;
  if (r.status === 'pending') return `${head}：有结果会通知你`;
  if (r.status === 'approved') {
    return r.task_id ? `${head}，已用这段文字发出一单` : `${head}：原样再点一次发布就行（放行一单，改了文字要重新判断）`;
  }
  return `${head}：${r.decision_note}。按理由改写后再发`;
}
