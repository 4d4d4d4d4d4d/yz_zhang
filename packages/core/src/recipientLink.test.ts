import { describe, expect, it } from 'vitest';
import { recipientLinkLine, recipientLinkUrl, recipientProgressLines } from './recipientLink';
import type { RecipientProgress } from './types';

const base: RecipientProgress = {
  recipient_label: '我妈', title: '修水龙头', phase: 'assigned', phase_text: '已经定好人了',
  helpers: [{ name: '李师傅', verified: true, work_date: null }], work_date: '2026-11-05', days: 1,
  shift_start: '09:00', shift_end: '11:00', deadline: null, visits_planned: 0, visits_reported: 0,
  last_arrival_at: null, expires_at: '2026-11-10T00:00:00Z',
};

describe('SCN-122 服务对象进度链接', () => {
  it('发单人面板说清链接状态与被打开的次数', () => {
    expect(recipientLinkLine(null)).toContain('还没有生成');
    const s = { state: 'active' as const, task_id: 1, created_at: '2026-11-03T00:00:00Z', expires_at: '2026-11-10T00:00:00Z', view_count: 0, last_viewed_at: null };
    expect(recipientLinkLine(s)).toContain('还没被打开过');
    expect(recipientLinkLine({ ...s, view_count: 3, last_viewed_at: '2026-11-04T01:00:00Z' })).toContain('已被打开 3 次');
    expect(recipientLinkLine({ ...s, state: 'expired' })).toContain('已过期');
    expect(recipientLinkLine({ ...s, state: 'revoked' })).toContain('已作废');
  });

  it('完整地址拼得对', () => {
    expect(recipientLinkUrl('https://x.cn/', '/r/abc')).toBe('https://x.cn/r/abc');
    expect(recipientLinkUrl('https://x.cn', 'r/abc')).toBe('https://x.cn/r/abc');
  });

  it('进度页几行人话：谁来、哪天几点、到没到', () => {
    const lines = recipientProgressLines(base);
    expect(lines[0]).toBe('我妈，这一单已经定好人了');
    expect(lines).toContain('来的人：李师傅（已实名）');
    expect(lines).toContain('时间：2026-11-05 09:00~11:00（北京时间）');
    expect(lines).toContain('还没有到达记录');
    const later = recipientProgressLines({ ...base, visits_planned: 2, visits_reported: 1, last_arrival_at: '2026-11-05T01:10:00Z', days: 3 });
    expect(later).toContain('上门：计划 2 次，已回报 1 次');
    expect(later.some((l) => l.startsWith('最近一次到达：'))).toBe(true);
    expect(later.some((l) => l.includes('起共 3 天'))).toBe(true);
    const noTime = recipientProgressLines({ ...base, work_date: null, shift_start: '', shift_end: '', deadline: '2026-11-06T10:00:00Z', helpers: [] });
    expect(noTime.some((l) => l.startsWith('最晚 '))).toBe(true);
    expect(noTime.some((l) => l.startsWith('来的人'))).toBe(false);
  });
});
