// APP-095（283 号 spec）合约卡片上「开票」入口的显示条件：放款（全额放款或按纠纷分账）之后、发布方本人才看到。
// 服务端照旧拦（not_party / not_settled），显示错了也开不出票——但会多一个按不通的按钮，所以单独测住。
import type { Contract } from '@platform/core';

export function canRequestInvoice(contract: Pick<Contract, 'status' | 'requester_id'>, meId: number | null | undefined): boolean {
  return ['released', 'split'].includes(contract.status) && meId === contract.requester_id;
}
