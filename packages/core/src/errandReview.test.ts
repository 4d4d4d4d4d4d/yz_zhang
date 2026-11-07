import { describe, expect, it } from 'vitest';
import { canRequestErrandReview, errandReviewLine } from './errandReview';
import type { ErrandReviewItem } from './types';

const base: ErrandReviewItem = {
  id: 1, kind: 'ghostwrite', kind_label: '代写学位论文代考', title: '论文集宣传', description: '', explanation: '是宣传文案',
  status: 'pending', decision_note: '', task_id: null, created_at: '2026-10-30T00:00:00Z', decided_at: null,
};

describe('SCN-219 发单拦截的人工复核', () => {
  it('只有只看文字、会误拦的几类拦截给复核入口', () => {
    expect(canRequestErrandReview('academic_ghostwriting')).toBe(true);
    expect(canRequestErrandReview('errand_restricted')).toBe(true);
    expect(canRequestErrandReview('fake_traffic')).toBe(true);
    expect(canRequestErrandReview('fake_inspection')).toBe(true);   // SCN-231（342 号 spec）
    expect(canRequestErrandReview('voice_clone')).toBe(true);       // SCN-234（344 号 spec）
    expect(canRequestErrandReview('odometer_fraud')).toBe(true);    // SCN-243（351 号 spec）
    expect(canRequestErrandReview('k12_tutoring_not_allowed')).toBe(false);
    expect(canRequestErrandReview('content_rejected')).toBe(false);
    expect(canRequestErrandReview(undefined)).toBe(false);
  });
  it('每个状态都说清下一步', () => {
    expect(errandReviewLine(base)).toContain('有结果会通知你');
    expect(errandReviewLine({ ...base, status: 'approved' })).toContain('原样再点一次发布');
    expect(errandReviewLine({ ...base, status: 'approved', task_id: 9 })).toContain('已用这段文字发出一单');
    expect(errandReviewLine({ ...base, status: 'rejected', decision_note: '就是代写' })).toContain('就是代写');
  });
});
