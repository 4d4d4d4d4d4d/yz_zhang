// API-056（235 号 spec）账号配额的一句话。
import { describe, expect, it } from 'vitest';
import { accountQuotaNote } from './apiQuota';

describe('API-056 accountQuotaNote', () => {
  it('没调过不写；调过写明，有到期日的写到哪天', () => {
    expect(accountQuotaNote({})).toBe('');
    expect(accountQuotaNote({ account_quota_custom: false, account_quota_expires_at: null })).toBe('');
    expect(accountQuotaNote({ account_quota_custom: true, account_quota_expires_at: null })).toBe('平台为你单独调过账号配额');
    const note = accountQuotaNote({ account_quota_custom: true, account_quota_expires_at: '2026-11-21T02:00:00Z' });
    expect(note.startsWith('平台为你单独调过账号配额（到 ')).toBe(true);
    expect(note).toContain('2026');
    expect(note.endsWith('，之后恢复默认）')).toBe(true);
  });
});
