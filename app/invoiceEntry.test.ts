import { canRequestInvoice } from './invoiceEntry';

describe('APP-095 合约卡片开票入口', () => {
  it('放款或分账之后、发布方本人才看到', () => {
    expect(canRequestInvoice({ status: 'released', requester_id: 9 }, 9)).toBe(true);
    expect(canRequestInvoice({ status: 'split', requester_id: 9 }, 9)).toBe(true);
  });
  it('执行方、别人、未登录都看不到', () => {
    expect(canRequestInvoice({ status: 'released', requester_id: 9 }, 3)).toBe(false);
    expect(canRequestInvoice({ status: 'released', requester_id: 9 }, null)).toBe(false);
    expect(canRequestInvoice({ status: 'released', requester_id: 9 }, undefined)).toBe(false);
  });
  it('还没放款的各个状态都看不到', () => {
    for (const status of ['pending_sign', 'signed', 'funded', 'in_progress', 'delivered', 'disputed', 'refunded', 'cancelled']) {
      expect(canRequestInvoice({ status, requester_id: 9 } as never, 9)).toBe(false);
    }
  });
});
