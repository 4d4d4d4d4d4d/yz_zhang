// 任务详情操作可见性矩阵（03/05 号 spec 的角色×状态规则，Web/App 共用）。
// 纯函数：给定任务/合约状态与当前用户，返回此刻允许展示的操作集合。
// 把「谁在什么状态下能做什么」钉成单一事实来源，避免两端各写一套漂移。

export type TaskActionId =
  | 'apply'             // 报名接单（TASK-010）
  | 'view_applications' // 查看报名并选人（TASK-020）
  | 'sign'              // 签署合约（SC-002）
  | 'wait_counterparty' // 已签，等待对方签署
  | 'fund'              // 托管资金（SC-003）
  | 'deliver'           // 提交验收（TASK-023）
  | 'accept_delivery'   // 验收通过放款（SC-005）
  | 'reject_delivery'   // 驳回返工（TASK-024）
  | 'open_dispute'      // 发起纠纷（DSP-001）
  | 'cancel'            // 取消（SC-006 规则计费）
  | 'review';           // 互评（TASK-027）

export interface TaskLike {
  status: string;
  creator_id: number;
  executor_id?: number | null;
}

export interface ContractLike {
  status: string;
  requester_id: number;
  executor_id: number;
  signed_by_requester: boolean;
  signed_by_executor: boolean;
  frozen: boolean;
}

export function taskActions(
  task: TaskLike, meId: number | null, contract?: ContractLike | null,
): TaskActionId[] {
  if (meId == null) return [];
  const isCreator = meId === task.creator_id;
  const isExecutor = meId === task.executor_id;
  const isParty = isCreator || isExecutor;
  const out: TaskActionId[] = [];

  switch (task.status) {
    case 'published':
      if (isCreator) out.push('view_applications');
      else out.push('apply');
      break;
    case 'matched':
      if (contract && !contract.frozen && isParty) {
        if (contract.status === 'pending_signatures') {
          const mySigned = isCreator ? contract.signed_by_requester : contract.signed_by_executor;
          out.push(mySigned ? 'wait_counterparty' : 'sign');
        } else if (contract.status === 'signed' && isCreator) {
          out.push('fund');
        }
      }
      if (isParty) out.push('cancel', 'open_dispute');
      break;
    case 'in_progress':
      if (isExecutor) out.push('deliver');
      if (isParty) out.push('cancel', 'open_dispute');
      break;
    case 'pending_acceptance':
      if (isCreator) out.push('accept_delivery', 'reject_delivery');
      if (isParty) out.push('open_dispute'); // 待验收不可单方取消（TASK-026）
      break;
    case 'completed':
      if (isParty) out.push('review');
      break;
    default:
      break; // draft/cancelled/disputed：详情页无直接操作
  }
  return out;
}


/** IM-009 报价卡：消息内容是服务端写的 JSON；解析不了（旧消息、被撤回）就返回 null，界面照普通消息显示。 */
export interface QuoteCard {
  task_id: number;
  price_cents: number;
  note: string;
  /** V144 起服务端写入的快照；更早的卡片没有，界面退回显示任务编号 */
  title?: string;
  /** 发起方是不是这单的发布方：是 → 对方可以「按这个价报名」；否 → 发布方去任务页选 TA */
  from_creator?: boolean;
}

export function parseQuoteCard(content: string): QuoteCard | null {
  try {
    const v = JSON.parse(content) as Partial<QuoteCard>;
    return typeof v.task_id === 'number' && typeof v.price_cents === 'number'
      ? { note: '', ...v } as QuoteCard : null;
  } catch {
    return null;
  }
}


/** SC-007b 一张变更单改了什么，一句话（两端共用，说法一致）。 */
export function describeChangeOrder(
  r: { new_amount_cents: number; new_deadline?: string | null; scope_change?: string },
  currentAmountCents: number, formatTime: (iso: string) => string,
): string {
  const parts: string[] = [];
  if (r.new_amount_cents !== currentAmountCents || (!r.new_deadline && !r.scope_change)) {
    parts.push(`改为 ¥${(r.new_amount_cents / 100).toFixed(2)}`);   // 沿用原来的文案「改为 ¥X」
  }
  if (r.new_deadline) parts.push(`截止改为 ${formatTime(r.new_deadline)}`);
  if (r.scope_change) parts.push(`范围：${r.scope_change}`);
  return parts.join('；');
}
