// SEC-061d 后台按角色显示板块（165 号 spec）：与服务端 roles_of / has_role 同一套规则。
import { describe, expect, it } from 'vitest';
import { adminRolesOf, canSeeAdminSection, hiddenAdminSections } from './adminSections';

const admin = (roles: string[]) => ({ is_admin: true, admin_roles: roles as never[] });

describe('SEC-061d 后台板块按角色', () => {
  it('没分配过角色的管理员按超级管理员对待；不是管理员什么都看不到', () => {
    expect(adminRolesOf(admin([]))).toEqual(['super']);
    expect(canSeeAdminSection(admin([]), 'finance')).toBe(true);
    expect(adminRolesOf({ is_admin: false, admin_roles: [] })).toEqual([]);
    expect(canSeeAdminSection({ is_admin: false, admin_roles: [] }, 'metrics')).toBe(false);
    expect(adminRolesOf(admin(['bogus']))).toEqual(['super']);
  });

  it('财务只看到自己的板块与人人可看的总览；隐藏的按顺序列出', () => {
    const fin = admin(['finance']);
    expect(canSeeAdminSection(fin, 'withdraw')).toBe(true);
    expect(canSeeAdminSection(fin, 'finance')).toBe(true);
    expect(canSeeAdminSection(fin, 'metrics')).toBe(true);
    expect(canSeeAdminSection(fin, 'packs')).toBe(false);
    expect(canSeeAdminSection(fin, 'tickets')).toBe(false);
    expect(hiddenAdminSections(fin)).toContain('服务包');
    expect(hiddenAdminSections(fin)).not.toContain('提现复核');
    expect(hiddenAdminSections(admin(['super']))).toEqual([]);
  });

  it('多个角色取并集', () => {
    const two = admin(['support', 'ops']);
    expect(canSeeAdminSection(two, 'tickets') && canSeeAdminSection(two, 'packs')).toBe(true);
    expect(canSeeAdminSection(two, 'aml')).toBe(false);
  });
});
