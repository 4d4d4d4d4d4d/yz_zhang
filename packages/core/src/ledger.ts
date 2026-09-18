// SYNC-001 账本科目的中文名：**全仓唯一一份**。
//
// 这张表原本写在 web/src/pages/Wallet.tsx 里，8 条。服务端实际能产生 20 条。
// 也就是说 12 种流水在用户的账单里显示为英文标识符——其中包括保证金冻结
// （`deposit_hold`）这种「可用余额凭空少了一笔」的日常路径。
//
// 它能漂这么久，是因为渲染端写的是 `KIND_LABEL[kind] ?? kind`：
// **少一条不会出错，只会给用户看英文**。这个兜底本身是对的（一笔认不出的
// 流水应当显示原始标识符，而不是让整个钱包页空白），所以防漂的责任不在
// 渲染时，在 CI——见 server/tests/test_shared_contract_drift.py：
// 服务端的 `LEDGER_KINDS` 与这张表的键必须**双向相等**，少一条或多一条都红。
//
// 放在 SDK 而不是 Web 里，是为了让「唯一一份」在物理上成立：
// 留在 Web 里，App 要显示流水就只能再抄一份，于是从两份变三份。

/** 账本科目 → 中文名。键集合必须与服务端 `wallet.service.LEDGER_KINDS` 相等。 */
export const LEDGER_KIND_LABEL: Record<string, string> = {
  // —— 出入金 ——
  topup: '充值',
  withdraw: '提现',
  withdraw_hold: '提现冻结',
  withdraw_refund: '提现失败退回',

  // —— 任务托管 ——
  escrow_hold: '资金托管',
  escrow_release: '任务收入',
  refund: '退款',
  fee: '平台佣金',

  // —— 保证金（CRED-005）——
  deposit_hold: '保证金冻结',
  deposit_return: '保证金退还',
  deposit_forfeit: '违约保证金',

  // —— 纠纷 ——
  dispute_split: '纠纷分割',

  // —— 平台账户（普通用户看不到，合规官/对账会看）——
  platform_topup: '平台资金注入',
  platform_settle: '平台结算',

  // —— 代扣税（TAX）——
  tax_withheld: '代扣个人所得税',
  tax_remit: '税款缴库',

  // —— 内部调整与补贴：transfer() 拼出来的 in/out 两向 ——
  adjust_in: '账务调整转入',
  adjust_out: '账务调整转出',
  subsidy_in: '平台补贴',
  subsidy_out: '补贴支出',

  // —— 平台自有 AI 助理收入归集（AGT-019）——
  agent_payout_in: 'AI 助理收入归集',
  agent_payout_out: 'AI 助理收入划出',

  // —— 人类核验（VER-010）——
  verify_hold: '核验费预扣',
  verify_payout: '核验报酬',
  verify_refund: '核验费退回',

  // —— 早期合作体收益分配（COOP-020）——
  coop_distribution_in: '合作体收益分配',
  coop_distribution_out: '合作体分配支出',

  // —— 团队支出（TEAM-020）——
  team_spend_in: '团队拨款',
  team_spend_out: '团队支出',
};

/** 认不出的科目显示原始标识符——宁可给用户一串能发给客服的字符，
 *  也不要让钱包页空白或报错。防漂交给 CI。 */
export function ledgerKindLabel(kind: string): string {
  return LEDGER_KIND_LABEL[kind] ?? kind;
}

/** 保证金状态（`Contract.deposit_status`）。`none` 表示这单没有保证金。 */
export const DEPOSIT_STATUS_LABEL: Record<string, string> = {
  none: '无',
  held: '冻结中',
  returned: '已退还',
  forfeited: '已罚没',
};
