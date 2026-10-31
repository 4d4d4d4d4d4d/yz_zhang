// ESCA-059（218 号 spec）提单人补充之后的提示。两端共用。
import { describe, expect, it } from 'vitest';
import { ticketReplyNotice } from './tickets';

describe('ESCA-059 ticketReplyNotice', () => {
  it('只说谢谢：保持已解决，并说清怎样才会重开', () => {
    expect(ticketReplyNotice({ id: 7, reopened: false, kept_closed: true })).toBe('收到，工单 #7 保持已解决；如果问题还在，写清哪里不对就会重新打开');
  });
  it('重新打开与普通补充与以前一样', () => {
    expect(ticketReplyNotice({ id: 7, reopened: true, kept_closed: false })).toBe('已补充，工单 #7 重新打开');
    expect(ticketReplyNotice({ id: 7, reopened: false })).toBe('已补充到工单 #7');
  });
});
