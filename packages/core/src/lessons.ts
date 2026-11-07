// KB-063b（326 号 spec）核验人写理由时就引导说具体。判据与服务端 verify.service.lesson_useful 同一条
// （空话表逐字相同，server/tests/test_lesson_quality.py 比对两边）：理由或修正方向至少一处说得出
// 「哪里不对」或「怎么改」——去掉标点空白至少 6 个字，且不是一句空话。

export const LESSON_MIN_CHARS = 6;

export const VAGUE_LESSONS: readonly string[] = [
  '不行', '不好', '不对', '不满意', '不合格', '不通过', '差', '太差', '很差', '一般', '还行', '还可以',
  '重做', '再改改', '不符合要求', '有问题', '质量不行', '质量差', '不太行', '凑合',
  '做得不好请重做', '完全不符合要求', '没达到我的要求', '不满意请重新做', '质量不行重新做', '效果不好再改改',
  '和预期不一样', '不是我想要的',
];

function specific(text: string): boolean {
  const t = (text ?? '').replace(/[^\p{L}\p{N}\p{M}]+/gu, '');
  return t.length >= LESSON_MIN_CHARS && !VAGUE_LESSONS.includes(t);
}

export function lessonSpecific(reason: string, revision = ''): boolean {
  return specific(reason) || specific(revision);
}

/** 核验页「没通过」时理由写得太空的提醒（不拦提交）。两端同一句。 */
export const VAGUE_LESSON_HINT = '这句没说清哪里不对：写具体些（哪一项没做到、要怎么改），下一单的人和 AI 才用得上；空话不会进经验库。';
