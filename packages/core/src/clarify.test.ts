import { describe, expect, it } from 'vitest';
import { clarifyProgressLine, clarifyPublishQuery, clarifyTemplate } from './clarify';
import type { ClarifyResult } from './types';

const draft = { title: '家里要打扫一下', description: '家里要打扫一下\n地点：上海', category: '保洁', is_remote: false, budget_cents: 30000, on_behalf_hint: false };
const base: ClarifyResult = { questions: [], draft, ready: true, blocked: null, remaining_required: 0 };

describe('AI-DEC-001 对话式需求澄清', () => {
  it('草稿变成发布页模板与查询参数（有预算才带）', () => {
    const t = clarifyTemplate(draft);
    expect(t).toMatchObject({ title: '家里要打扫一下', category: '保洁', description: draft.description, visits_planned: 0 });
    const q = new URLSearchParams(clarifyPublishQuery(draft));
    expect(q.get('title')).toBe('家里要打扫一下');
    expect(q.get('category')).toBe('保洁');
    expect(q.get('budget')).toBe('300');
    expect(new URLSearchParams(clarifyPublishQuery({ ...draft, budget_cents: null })).has('budget')).toBe(false);
  });

  it('进度一行：被拦下给原因、没问完给还差几件、问完说可以带到发布页', () => {
    expect(clarifyProgressLine({ ...base, ready: false, remaining_required: 2, questions: [{ key: 'when', ask: '?', required: true, options: [] }] })).toBe('还差 2 件要问清楚');
    expect(clarifyProgressLine(base)).toContain('都问清楚了');
    expect(clarifyProgressLine({ ...base, questions: [{ key: 'budget', ask: '?', required: false, options: [] }] })).toContain('选答');
    expect(clarifyProgressLine({ ...base, ready: false, blocked: { code: 'errand_restricted', message: '平台不承接代开处方药' } })).toBe('平台不承接代开处方药');
  });
});
