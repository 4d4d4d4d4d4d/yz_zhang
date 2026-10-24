// SEC-061h 板块里的按钮级权限（295 号 spec）：与服务端 has_role 同一套规则。
import { describe, expect, it } from 'vitest';
import { adminActionHint, canDoAdminAction } from './adminSections';

const admin = (roles: string[]) => ({ is_admin: true, admin_roles: roles as never[] });

describe('SEC-061h 按钮按角色', () => {
  it('封禁、解封只给合规（和超级管理员）；客服看得到用户板块但按不了', () => {
    expect(canDoAdminAction(admin(['support']), 'banUser')).toBe(false);
    expect(canDoAdminAction(admin(['support']), 'unbanUser')).toBe(false);
    expect(canDoAdminAction(admin(['compliance']), 'banUser')).toBe(true);
    expect(canDoAdminAction(admin(['support', 'compliance']), 'unbanUser')).toBe(true);
    expect(canDoAdminAction(admin([]), 'banUser')).toBe(true);
    expect(canDoAdminAction({ is_admin: false, admin_roles: [] }, 'banUser')).toBe(false);
  });

  it('指派工单只给超级管理员', () => {
    expect(canDoAdminAction(admin(['support']), 'assignTicket')).toBe(false);
    expect(canDoAdminAction(admin(['super']), 'assignTicket')).toBe(true);
  });

  it('按不了的按钮换成一句「这件事要谁来做」', () => {
    expect(adminActionHint('banUser')).toBe('封禁用户要合规来做');
    expect(adminActionHint('assignTicket')).toBe('指派工单要超级管理员来做');
  });
});
