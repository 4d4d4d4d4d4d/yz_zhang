// SEC-061d 管理后台按角色显示板块（165 号 spec）。
//
// 服务端早就按角色在事前拦（141 号 spec），可后台把所有板块都画出来：财务点开「场景包」看到一屏 403，
// 运营的页面上挂着提现复核。这里给每个板块记下它**加载数据用的那个接口**（probe）和能看它的角色；
// 闸门 `server/tests/test_admin_sections.py` 逐条核对：roles 必须**恰好等于**服务端给那个接口定的角色——
// 界面多显示一个角色，他点开就是 403；少显示一个，他有权限却找不到入口。
import type { AdminRoleKey, Me } from './types';

export const ALL_ADMIN_ROLES: readonly AdminRoleKey[] = ['super', 'support', 'arbiter', 'compliance', 'finance', 'ops'];

export interface AdminSection {
  label: string;
  probe: string;
  roles: readonly AdminRoleKey[];
}

export const ADMIN_SECTIONS = {
  metrics: { label: '平台指标', probe: 'GET /admin/metrics', roles: ALL_ADMIN_ROLES },
  // APP-094（184 号 spec）
  clientErrors: { label: '页面出错', probe: 'GET /admin/client-errors', roles: ['ops'] },
  roles: { label: '管理员与角色', probe: 'GET /admin/roles', roles: ALL_ADMIN_ROLES },
  launch: { label: '上线准备', probe: 'GET /admin/vendors', roles: ALL_ADMIN_ROLES },
  queues: { label: '人审队列总览', probe: 'GET /admin/queues', roles: ALL_ADMIN_ROLES },
  withdraw: { label: '提现复核', probe: 'GET /wallet/withdraw-requests', roles: ['finance'] },
  aml: { label: '可疑活动', probe: 'GET /admin/aml/activities', roles: ['compliance'] },
  knowledge: { label: '经验库', probe: 'GET /admin/knowledge/overview', roles: ['ops'] },
  packs: { label: '服务包', probe: 'GET /admin/packs', roles: ['ops'] },
  legal: { label: '法律知识', probe: 'GET /admin/legal/faqs', roles: ['compliance'] },
  sandbox: { label: '端侧模型', probe: 'GET /admin/sandbox/models', roles: ['ops'] },
  skills: { label: '技能概念', probe: 'GET /admin/skill-concepts', roles: ['ops'] },
  teams: { label: '团队企业核验', probe: 'GET /admin/teams/pending', roles: ['compliance'] },
  certifications: { label: '资质核验', probe: 'GET /admin/certifications/pending', roles: ['compliance'] },
  uploads: { label: '上传审核', probe: 'GET /admin/uploads/pending', roles: ['compliance'] },
  tickets: { label: '客服工单', probe: 'GET /admin/tickets', roles: ['support'] },
  reports: { label: '举报处置', probe: 'GET /admin/reports', roles: ['support', 'compliance'] },
  users: { label: '用户管理', probe: 'GET /admin/users', roles: ['support', 'compliance'] },
  security: { label: '安全看板', probe: 'GET /admin/security', roles: ['compliance'] },
  cities: { label: '城市与类目', probe: 'POST /admin/cities', roles: ['ops'] },
  audit: { label: '审计日志', probe: 'GET /admin/audit-log', roles: ['compliance'] },
  finance: { label: '平台财务', probe: 'GET /admin/platform-finance', roles: ['finance'] },
  announcements: { label: '全站公告', probe: 'GET /admin/announcements', roles: ['ops'] },
  // API-056（235 号 spec）
  apiQuotas: { label: '开放 API 配额', probe: 'GET /admin/api-accounts/quotas', roles: ['ops'] },
} satisfies Record<string, AdminSection>;

export type AdminSectionKey = keyof typeof ADMIN_SECTIONS;

/** 生效的角色：与服务端 `roles_of` 一致——没分配过角色的管理员按超级管理员对待。 */
export function adminRolesOf(me: Pick<Me, 'is_admin' | 'admin_roles'> | null | undefined): AdminRoleKey[] {
  if (!me?.is_admin) return [];
  const granted = (me.admin_roles ?? []).filter((r) => ALL_ADMIN_ROLES.includes(r));
  return granted.length ? granted : ['super'];
}

export function canSeeAdminSection(me: Pick<Me, 'is_admin' | 'admin_roles'> | null | undefined, key: AdminSectionKey): boolean {
  const mine = adminRolesOf(me);
  return mine.includes('super') || ADMIN_SECTIONS[key].roles.some((r) => mine.includes(r));
}

/** 看不到的板块（给页脚一句话：「这些板块不在你的职责里」），按顺序 */
export function hiddenAdminSections(me: Pick<Me, 'is_admin' | 'admin_roles'> | null | undefined): string[] {
  return (Object.keys(ADMIN_SECTIONS) as AdminSectionKey[]).filter((k) => !canSeeAdminSection(me, k)).map((k) => ADMIN_SECTIONS[k].label);
}
