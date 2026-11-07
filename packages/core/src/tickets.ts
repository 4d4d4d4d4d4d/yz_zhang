import type { MyTicketReplied } from './types';

/** ESCA-056 / ESCA-059（218 号 spec）提单人补充之后的一句话：重新打开了、只是补充了、还是只说了谢谢保持已结。两端同一句。 */
export function ticketReplyNotice(r: Pick<MyTicketReplied, 'id' | 'reopened' | 'kept_closed'>): string {
  if (r.kept_closed) return `收到，工单 #${r.id} 保持已解决；如果问题还在，写清哪里不对就会重新打开`;
  return r.reopened ? `已补充，工单 #${r.id} 重新打开` : `已补充到工单 #${r.id}`;
}
