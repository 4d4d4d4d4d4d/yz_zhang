// PACK-100 服务包（123 号 spec）：浏览、启用、问助手专家（带出处与人工关口）、运营台的四眼与雷达。
import { PlatformClient } from '@platform/core';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = {
  id: 2, phone: '138****0002', nickname: '我', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100,
  rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2',
};
const CARD = {
  key: 'collab-basics', version: 1, title: '平台协作入门', segment: 'general', summary: '一页讲清托管、验收、纠纷',
  pains: ['不知道钱什么时候付'], enabled: false, enabled_version: null, upgrade_available: false, active_users: 3,
  published_at: '2026-10-13T00:00:00Z',
  assets: {
    assistants: [{ key: 'collab-advisor', name: '协作顾问', persona: '熟悉平台规则', inputs: ['问题'], outputs: ['说明'],
      forbidden: ['替你付款'], tools: ['pack.knowledge'], human_gates: ['付款、收款、转账、托管'] }],
    methods: [{ key: 'm', name: '接单前确认清单', steps: 5 }],
    knowledge: [{ key: 'k', title: '钱先托管在平台', kind: 'rule', source: '平台服务规则：资金托管', valid_until: null }],
    routines: [{ key: 'r', name: '每周回顾', freq: 'weekly', time_of_day: '18:00' }], task_templates: [],
  },
};
type Call = { method: string; path: string; body?: unknown };

function open(path: string, routes: Record<string, unknown>, calls: Call[] = [], me = ME) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const key = Object.keys(routes).find((k) => k === `${method} ${p}`) ?? Object.keys(routes).find((k) => k === p);
    return { ok: true, status: 200, text: async () => JSON.stringify(key ? routes[key] : (p === '/users/me' ? me : [])) };
  }) as unknown as typeof fetch;
  const client = new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
  render(<MemoryRouter initialEntries={[path]}><AppProvider client={client}><App /></AppProvider></MemoryRouter>);
  return calls;
}

describe('PACK-100 服务包', () => {
  it('导航多了「服务包」，原有导航项一个不少；列表写清解决什么、有什么', async () => {
    open('/packs', { '/packs': [CARD] });
    const nav = await screen.findByRole('navigation', { name: '工作台导航' });
    for (const label of ['发现', '合作', '工作台', '知识库', '服务包', '消息', '我的空间']) expect(nav.textContent).toContain(label);
    expect(await screen.findByRole('button', { name: '平台协作入门' })).toBeTruthy();
    expect(screen.getByText(/1 位助手专家 · 1 份做法清单 · 1 条知识 · 1 个定时提醒 · 3 人在用/)).toBeTruthy();
  });

  it('启用：可以不要定时提醒；装了什么写清楚', async () => {
    const calls: Call[] = [];
    open('/packs?pack=collab-basics', { '/packs': [CARD], '/packs/collab-basics': CARD,
      'POST /packs/collab-basics/enable': { ...CARD, enabled: true, enabled_version: 1, installed: { methods: 1, notes: 1, routines: 0 } } }, calls);
    fireEvent.click(await screen.findByLabelText(/同时打开定时提醒/));
    fireEvent.click(screen.getByRole('button', { name: '启用' }));
    await waitFor(() => expect(calls.find((c) => c.path === '/packs/collab-basics/enable')?.body).toEqual({ with_routines: false }));
    expect((await screen.findByRole('status')).textContent).toContain('1 份做法、1 条知识、0 个定时提醒');
  });

  it('发单模板只预填发布页', async () => {
    const withTpl = { ...CARD, assets: { ...CARD.assets, task_templates: [{ key: 't', title: '记账代理', category: '财税', description: '每月记账\n\n验收标准：\n- 按月交凭证' }] } };
    open('/packs?pack=collab-basics', { '/packs': [withTpl], '/packs/collab-basics': withTpl });
    const link = await screen.findByRole('link', { name: '用这个模板发单' });
    const href = new URL(link.getAttribute('href') ?? '', 'http://x');
    expect(href.pathname).toBe('/publish');
    expect(href.searchParams.get('title')).toBe('记账代理');
    expect(href.searchParams.get('description')).toContain('验收标准');
  });

  it('问助手专家：每条带出处，过期的标出来，人工关口写在下面；答不了给发单入口', async () => {
    open('/packs?pack=collab-basics', { '/packs': [CARD], '/packs/collab-basics': CARD,
      'POST /packs/collab-basics/assistants/collab-advisor/ask': { assistant: '协作顾问', gates: ['付款、收款、转账、托管'],
        gate_notice: '这些事助手只给草稿，必须你本人确认后再做：付款、收款、转账、托管', refused: false, answer: '…', remedy: null,
        citations: [{ n: 1, kind: 'pack', title: '验收期限', snippet: '默认 3 天', source: '平台服务规则：验收', valid_until: '2020-01-01', expired: true, note_id: null }] } });
    fireEvent.change(await screen.findByLabelText('问协作顾问'), { target: { value: '验收过期会怎样' } });
    fireEvent.click(screen.getByRole('button', { name: '问' }));
    const box = await screen.findByLabelText('助手的回答');
    expect(box.textContent).toContain('出处：平台服务规则：验收');
    expect(box.textContent).toContain('已过有效期');
    expect(box.textContent).toContain('必须你本人确认');
  });

  it('运营台：写它的人不能自己批（上线按钮禁用），校验问题逐条列出，雷达显示依据', async () => {
    const calls: Call[] = [];
    const row = (id: number, status: string, created_by: number) => ({ id, key: `k${id}`, version: 1, title: `包${id}`, segment: 'general', status,
      score: 10, created_by, reviewed_by: null, published_at: null, retired_reason: '', updated_at: '', definition: {},
      metrics: { active: 0, enabled_total: 0, asks_30d: 0, unanswered_30d: 0, helpful_30d: 0, unhelpful_30d: 0, unanswered_rate: null, helpful_rate: null } });
    open('/admin', {
      '/users/me': { ...ME, is_admin: true },
      'GET /admin/packs': [row(1, 'review', 2), row(2, 'review', 9)],
      '/admin/packs/radar': [{ source: 'search_gap', key: '宠物上门喂养', title: '有人在找「宠物上门喂养」，平台上没有', evidence: '近 30 天 4 个不同的人搜过', people: 4, suggested: {} },
        // SCN-221（340 号 spec）发单拦截某一类复核通过得多
        { source: 'errand_gap', key: '代写学位论文代考', title: '发单拦截「代写学位论文代考」可能拦得太宽', evidence: '近 30 天这一类复核处理了 4 条，通过 3 条', people: 3, suggested: {} }],
      'POST /admin/packs/validate': { ok: false, problems: ['助手「财税助手」服务高风险人群（opc），钱、签署、申报都必须是人工关口'], score: null },
      'POST /admin/packs/2/approve': row(2, 'published', 9),
    }, calls, { ...ME, is_admin: true });
    const panel = await screen.findByLabelText('服务包运营');
    await screen.findByText('包1');
    const approves = screen.getAllByRole('button', { name: '上线' }) as HTMLButtonElement[];
    expect(approves[0].disabled).toBe(true);
    expect(approves[1].disabled).toBe(false);
    fireEvent.click(approves[1]);
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/admin/packs/2/approve')).toBe(true));
    fireEvent.change(screen.getByLabelText('服务包定义'), { target: { value: '{"key": "x"}' } });
    fireEvent.click(screen.getByRole('button', { name: '校验' }));
    expect((await screen.findByLabelText('校验问题')).textContent).toContain('钱、签署、申报都必须是人工关口');
    expect(panel.textContent).toContain('近 30 天 4 个不同的人搜过');
    expect(screen.getByText('发单拦截「代写学位论文代考」可能拦得太宽').closest('tr')!.textContent).toContain('发单拦截可能误拦');
  });

  it('雷达一键起草知识条目：进选中的服务包草稿，编辑器打开它并提示把「【待填写】」写完', async () => {
    const calls: Call[] = [];
    const row = (id: number, key: string, status: string) => ({ id, key, version: 1, title: key, segment: 'general', status,
      score: 10, created_by: 9, reviewed_by: null, published_at: null, retired_reason: '', updated_at: '', definition: {},
      metrics: { active: 0, enabled_total: 0, asks_30d: 0, unanswered_30d: 0, helpful_30d: 0, unhelpful_30d: 0, unanswered_rate: null, helpful_rate: null } });
    const draft = { ...row(7, 'household-chores', 'draft'), version: 2,
      definition: { key: 'household-chores', knowledge: [{ key: 'radar-legal-gap-1', title: '婚姻家庭：常见问题怎么答', body: '【待填写】这里写', source: '【待填写】出处' }] } };
    open('/admin', {
      '/users/me': { ...ME, is_admin: true },
      'GET /admin/packs': [row(1, 'collab-basics', 'published'), row(3, 'household-chores', 'published')],
      '/admin/packs/radar': [{ source: 'legal_gap', key: '婚姻家庭', title: '「婚姻家庭」类法律问题常答不上', evidence: '近 30 天 3 个不同的人', people: 3, suggested: {} }],
      'POST /admin/packs/radar/draft-knowledge': { pack: draft, knowledge_key: 'radar-legal-gap-1', new_version: true, placeholders: 1 },
    }, calls, { ...ME, is_admin: true });
    await within(await screen.findByLabelText('服务包运营')).findByText('「婚姻家庭」类法律问题常答不上');
    fireEvent.change(screen.getByLabelText('起草进哪个服务包'), { target: { value: 'household-chores' } });
    fireEvent.click(screen.getByRole('button', { name: '起草知识条目' }));
    await waitFor(() => expect(calls.find((c) => c.path === '/admin/packs/radar/draft-knowledge')?.body)
      .toEqual({ source: 'legal_gap', key: '婚姻家庭', pack_key: 'household-chores' }));
    expect(await screen.findByText(/已起草进「household-chores」v2 的草稿.*【待填写】/)).toBeTruthy();
    expect((screen.getByLabelText('服务包定义') as HTMLTextAreaElement).value).toContain('radar-legal-gap-1');
    expect(screen.getByText('编辑草稿 #7')).toBeTruthy();
  });
});

describe('SCN-133 带清单的发单模板', () => {
  it('跳到发布页时带上上门次数与清单，发布页预填好', async () => {
    const tpl = { key: 'v', title: '异地代看房（按套）', category: '跑腿', description: '只看、拍、问', visits_planned: 1,
      visit_checklist: ['小区门口与楼栋号', '水电燃气表读数'] };
    const withTpl = { ...CARD, assets: { ...CARD.assets, task_templates: [tpl] } };
    open('/packs?pack=collab-basics', { '/packs': [withTpl], '/packs/collab-basics': withTpl });
    const link = await screen.findByRole('link', { name: '用这个模板发单' });
    const href = new URL(link.getAttribute('href') ?? '', 'http://x');
    expect([href.searchParams.get('visits'), href.searchParams.get('checklist')]).toEqual(['1', '小区门口与楼栋号、水电燃气表读数']);
    cleanup();
    open(`/publish?${href.searchParams.toString()}`, { '/categories': [{ name: '跑腿', required_cert: '' }] });
    expect(((await screen.findByLabelText('每次要做的事')) as HTMLInputElement).value).toBe('小区门口与楼栋号、水电燃气表读数');
    expect((screen.getByLabelText('要上门几次') as HTMLInputElement).value).toBe('1');
  });
});
