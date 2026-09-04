import { describe, expect, it } from 'vitest';
import { taskActions, type ContractLike, type TaskLike } from './actions';

const BOSS = 1, WORKER = 2, STRANGER = 9;

function task(status: string): TaskLike {
  return { status, creator_id: BOSS, executor_id: WORKER };
}

function contract(over: Partial<ContractLike> = {}): ContractLike {
  return {
    status: 'pending_signatures', requester_id: BOSS, executor_id: WORKER,
    signed_by_requester: false, signed_by_executor: false, frozen: false, ...over,
  };
}

describe('taskActions 角色×状态可见性矩阵（03/05 号 spec）', () => {
  it('未登录无任何操作', () => {
    expect(taskActions(task('published'), null)).toEqual([]);
  });

  it('published：发布者选人，他人报名', () => {
    expect(taskActions(task('published'), BOSS)).toEqual(['view_applications']);
    expect(taskActions(task('published'), STRANGER)).toEqual(['apply']);
  });

  it('matched 未签：当事人见「签署」，签过的见「等待对方」', () => {
    expect(taskActions(task('matched'), BOSS, contract()))
      .toEqual(['sign', 'cancel', 'open_dispute']);
    expect(taskActions(task('matched'), BOSS, contract({ signed_by_requester: true })))
      .toEqual(['wait_counterparty', 'cancel', 'open_dispute']);
    expect(taskActions(task('matched'), WORKER, contract({ signed_by_requester: true })))
      .toEqual(['sign', 'cancel', 'open_dispute']);
  });

  it('matched 双签：仅发布者见「托管」', () => {
    const signed = contract({ status: 'signed', signed_by_requester: true, signed_by_executor: true });
    expect(taskActions(task('matched'), BOSS, signed))
      .toEqual(['fund', 'cancel', 'open_dispute']);
    expect(taskActions(task('matched'), WORKER, signed))
      .toEqual(['cancel', 'open_dispute']);
  });

  it('冻结合约不出现签署/托管入口', () => {
    expect(taskActions(task('matched'), BOSS, contract({ frozen: true })))
      .toEqual(['cancel', 'open_dispute']);
  });

  it('in_progress：仅执行者可交付', () => {
    expect(taskActions(task('in_progress'), WORKER))
      .toEqual(['deliver', 'cancel', 'open_dispute']);
    expect(taskActions(task('in_progress'), BOSS))
      .toEqual(['cancel', 'open_dispute']);
  });

  it('pending_acceptance：发布者验收/驳回，双方可纠纷，均不可取消（TASK-026）', () => {
    expect(taskActions(task('pending_acceptance'), BOSS))
      .toEqual(['accept_delivery', 'reject_delivery', 'open_dispute']);
    expect(taskActions(task('pending_acceptance'), WORKER)).toEqual(['open_dispute']);
  });

  it('completed：当事人互评；路人在任何状态都无操作', () => {
    expect(taskActions(task('completed'), BOSS)).toEqual(['review']);
    expect(taskActions(task('completed'), WORKER)).toEqual(['review']);
    for (const s of ['matched', 'in_progress', 'pending_acceptance', 'completed', 'disputed']) {
      expect(taskActions(task(s), STRANGER)).toEqual([]);
    }
  });

  it('终局/纠纷中详情页无直接操作', () => {
    expect(taskActions(task('cancelled'), BOSS)).toEqual([]);
    expect(taskActions(task('disputed'), BOSS)).toEqual([]);
  });
});
